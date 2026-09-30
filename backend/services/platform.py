"""Service facade used by the API layer (keeps routes thin and every feature independently testable)."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta
from functools import cached_property

from sqlalchemy import func, select

from backend.agents.diagnostic_agent import SOLUTION_POOL
from backend.agents.graph import AgentOrchestrator
from backend.database.session import session_scope
from backend.evaluation.query_eval import evaluate_query as score_query
from backend.evidence.chain import assemble
from backend.intelligence.correlation import PRESETS
from backend.knowledge.evolution import KBEvolution
from backend.models.entities import (
    CorrelationAlert, EscalationHandoff, EscalationRecord, EscalationResolution, Incident, IncidentFeedback,
    IncidentFingerprint, KBEvolutionEvent, KnowledgeQuality,
)
from backend.rag.llm import RETRIEVAL_ONLY_LABEL
from backend.rag.resolution import rank_resolutions
from backend.rag.synthesis import synthesize, validate
from backend.services import postmortem as pm_service
from backend.services.analysis import analyze_text
from backend.services.incidents import create_live_incident, incident_row, update_incident
from backend.services.runtime import Runtime, get_runtime
from backend.services.triage import family_outcome_stats, route_team, route_tier
from backend.troubleshooting.attempts import AttemptTracker


def resolved_percent(rating: float) -> int:
    """Star rating (1-5) as the share of the incident that got resolved."""
    return round(max(0.0, min(5.0, float(rating))) / 5 * 100)


def _jsonable(obj):
    return json.loads(json.dumps(obj, default=str))


class Platform:
    def __init__(self, rt: Runtime | None = None):
        self.rt = rt or get_runtime()
        self._evidence_cache: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._last_refresh = 0.0

    def maybe_refresh_kb(self, min_interval_s: float = 60.0) -> int:
        """Records accepted by the kb-worker (another process) are merged into this process's store."""
        import time

        from backend.knowledge.evolution import load_accepted_additions

        if time.time() - self._last_refresh < min_interval_s:
            return 0
        self._last_refresh = time.time()
        with self.rt.lock:
            n = load_accepted_additions(self.rt.store)
            if n:
                self.rt.retriever.rebuild_bm25()
                from backend.intelligence.pattern_detection import PatternEngine
                fresh = PatternEngine.load(self.rt.s, self.rt.store, self.rt.embedder)
                self.rt.patterns.assign.update(fresh.assign)
                self.rt.patterns.fingerprints.update(fresh.fingerprints)
        return n

    @cached_property
    def agents(self) -> AgentOrchestrator:
        return AgentOrchestrator(self.rt)

    @cached_property
    def evolution(self) -> KBEvolution:
        return KBEvolution(self.rt, self.agents.sidx)

    # ------------------------------------------------------------------ helpers
    def _mode(self, bundle) -> list[str]:
        return list(bundle.retrieval.mode.labels) + ([] if self.rt.llm.available else [RETRIEVAL_ONLY_LABEL])

    def _classification(self, text: str, fields: dict) -> dict:
        pred = self.rt.outcome_models.classify_text(text) if self.rt.outcome_models.available else {}
        out = {}
        for f in ("category", "priority", "impact", "urgency"):
            if fields.get(f):
                out[f] = {"value": fields[f], "provenance": "original (reported)"}
            elif f in pred:
                out[f] = pred[f]
            else:
                out[f] = {"value": None, "provenance": "missing", "note": "no classifier available"}
        return out

    # ------------------------------------------------------------------ search
    def search(self, query: str, filters=None, top_k: int = 10, rerank: bool = True) -> dict:
        self.maybe_refresh_kb()
        bundle = analyze_text(self.rt, query, filters=filters, top_k=top_k, rerank=rerank)
        chain = assemble(self.rt, bundle, subject="retrieval")
        out = bundle.retrieval.model_dump(mode="json")
        out.update({"fingerprint": bundle.fingerprint.as_dict(), "families": _jsonable(bundle.families[:3]),
                    "novelty": bundle.novelty, "evidence_chain": _jsonable(chain), "mode_labels": self._mode(bundle),
                    "timings_ms": bundle.timer.timings_ms})
        return out

    # ------------------------------------------------------------------ analyze (agent graph)
    def analyze(self, text: str, title=None, fields=None, hints=None, filters=None, incident_id=None, top_k=10) -> dict:
        fields = fields or {}
        self.maybe_refresh_kb()
        iid = incident_id or create_live_incident(text, title=title, fields=fields)
        with self.rt.lock:
            state = self.agents.analyze(text, hints=hints, filters=filters, incident_id=iid, fields=fields, top_k=top_k,
                                        pool=SOLUTION_POOL)
        bundle = state["bundle"]
        diag = state.get("diagnostic") or {}
        ranking = diag.get("ranking")
        chain = assemble(self.rt, bundle, ranking, diag.get("synthesis"), diag.get("validation"),
                         subject="analysis")
        self._evidence_cache[iid] = _jsonable(chain)
        top = ranking["top"] if ranking else None
        fam = bundle.families[0] if bundle.families else None
        return _jsonable({
            "incident_id": iid,
            "classification": self._classification(text, fields),
            "novelty": bundle.novelty,
            "pattern_family": state["pattern"]["families"][0] if state["pattern"]["families"] else None,
            "family_causal_chain": state["pattern"]["family_causal_chain"],
            "likely_root_cause": chain["root_cause_evidence"],
            "top_resolution": top,
            "confidence": top["confidence"] if top else None,
            "confidence_basis": top["confidence_basis"] if top else "undetermined — no evidence-backed resolution",
            "llm_synthesis": diag.get("synthesis"), "llm_validation": diag.get("validation"),
            "alternatives": ranking["alternatives"][:4] if ranking else [],
            "top_solutions": ranking.get("solutions", [])[:5] if ranking else [],
            "filtered_as_irrelevant": ranking.get("filtered_as_irrelevant", []) if ranking else [],
            "blocked_by_guardrails": ranking["blocked_by_guardrails"] if ranking else [],
            "strategy_panel": diag.get("strategy_panel", self.agents.sidx.panel(fam["family_id"] if fam else None)),
            "similar_incidents": [r.model_dump(mode="json") for r in bundle.retrieval.results[:top_k]],
            "fingerprint": bundle.fingerprint.as_dict(),
            "escalation_proposal": state.get("escalation"),
            "query_evaluation": score_query(bundle, (ranking or {}).get("baseline_top") or top),
            "evidence_chain": chain,
            "agent_messages": state.get("messages", []),
            "mode_labels": self._mode(bundle),
            "timings_ms": bundle.timer.timings_ms,
        })

    # ------------------------------------------------------------------ per-query evaluation
    def evaluate_query(self, text: str) -> dict:
        """Evaluate one query without creating an incident record (unlike analyze)."""
        self.maybe_refresh_kb()
        with self.rt.lock:
            bundle = analyze_text(self.rt, text, top_k=10)
            fam = bundle.families[0] if bundle.families else None
            ranking = rank_resolutions(bundle.retrieval.results, self.agents.sidx, reranked=bundle.retrieval.mode.reranked,
                                       family=fam)
        return _jsonable({
            "query": text,
            "evaluation": score_query(bundle, ranking["top"]),
            "family": ({k: fam[k] for k in ("family_id", "name", "size", "match_strength")} if fam else None),
            "top_matches": [{"incident_id": r.incident_id, "title": r.title,
                             "relevance": r.scores.relevance_confidence} for r in bundle.retrieval.results[:3]],
            "mode_labels": self._mode(bundle),
        })

    # ------------------------------------------------------------------ triage
    def triage(self, text: str, fields=None, hints=None, filters=None, incident_id=None, top_k=10, **_) -> dict:
        fields = fields or {}
        bundle = analyze_text(self.rt, text, filters=filters, hints=hints, top_k=top_k)
        cls = self._classification(text, fields)
        fam = bundle.families[0] if bundle.families else None
        fam_obj = self.rt.patterns.families.get(fam["family_id"]) if fam else None
        fstats = family_outcome_stats(self.rt.store, fam_obj)
        prio = cls["priority"]["value"]
        tier = route_tier(self.rt.s.tiers, priority=prio, novel=bundle.novelty.get("is_novel"),
                          family_mean_reassignments=fstats.get("mean_reassignments"))
        team = route_team(bundle.fingerprint.values, category=cls["category"]["value"])
        ranking = rank_resolutions(bundle.retrieval.results, self.agents.sidx, reranked=bundle.retrieval.mode.reranked,
                                   family=bundle.families[0] if bundle.families else None)
        top = ranking["top"]
        rt_pred = self.rt.outcome_models.predict_resolution_hours({
            "priority": prio or "Not Set", "impact": cls["impact"]["value"] or "Not Set",
            "urgency": cls["urgency"]["value"] or "Not Set", "ticket_type": "incident",
            "ci_group": fields.get("ci_group", "Unknown"), "ci_subcategory": "Unknown"}) if self.rt.outcome_models.available else None
        fix = {"family_first_time_fix_rate": fstats.get("first_time_fix_rate") if fstats.get("stats_supported") else None,
               "family_outcome_basis": f"{fstats.get('n_with_outcome', 0)} family members with real Reopen_Time data"
               + ("" if fstats.get("stats_supported") else " (< 20: no rate shown)"),
               "recommended_strategy_reopen_rate": (top.get("strategy_stats") or {}).get("reopen_rate") if top else None,
               "recommended_strategy_basis": (top.get("strategy_stats") or {}).get("basis") if top else None}
        if self.rt.outcome_models.available and top:
            fix["model_reopen_risk"] = self.rt.outcome_models.reopen_risk({
                "priority": prio or "Not Set", "impact": cls["impact"]["value"] or "Not Set",
                "urgency": cls["urgency"]["value"] or "Not Set", "ticket_type": "incident",
                "closure_class": _closure_class_for(top, self.agents.sidx), "resolution_hours": (rt_pred or {}).get("predicted_hours_median", 1.0)})
        chain = assemble(self.rt, bundle, ranking, subject="triage")
        if incident_id:
            self._evidence_cache[incident_id] = _jsonable(chain)
        return _jsonable({
            "incident_id": incident_id, "classification": cls,
            "routing": {**team, **tier}, "resolution_time_prediction": rt_pred, "fix_accuracy": fix,
            "root_cause": chain["root_cause_evidence"], "family": fam, "family_outcome_history": fstats,
            "novelty": bundle.novelty, "fingerprint": bundle.fingerprint.as_dict(), "evidence_chain": chain,
            "mode_labels": self._mode(bundle), "timings_ms": bundle.timer.timings_ms,
        })

    # ------------------------------------------------------------------ resolve
    def resolve(self, text: str, hints=None, exclude_strategies=None, filters=None) -> dict:
        excluded = set(exclude_strategies or [])
        sidx = self.agents.sidx
        bundle = analyze_text(self.rt, text, hints=hints, filters=filters, top_k=10,
                              exclude_fn=(lambda rec: rec is not None and sidx.key_for(rec["incident_id"]) in excluded)
                              if excluded else None)
        with bundle.timer.stage("resolution_ranking"):
            ranking = rank_resolutions(bundle.retrieval.results, sidx, excluded, bundle.retrieval.mode.reranked,
                                       family=bundle.families[0] if bundle.families else None)
        if bundle.novelty.get("is_novel"):  # never force a low-confidence historical fix onto a novel incident
            ranking = {**ranking, "top": None, "alternatives": [], "novel_incident": bundle.novelty["verdict"]}
        with bundle.timer.stage("llm_generation"):
            synth = synthesize(self.rt.llm, text, ranking["top"]) if ranking["top"] else None
            check = validate(self.rt.llm, self.rt.embedder, synth, ranking["top"]) if synth else None
        with bundle.timer.stage("evidence_chain_assembly"):
            chain = assemble(self.rt, bundle, ranking, synth, check, subject="resolution")
        fam = bundle.families[0]["family_id"] if bundle.families else None
        return _jsonable({
            "top_resolution": ranking["top"], "alternatives_for_fallback": ranking["alternatives"],
            "novel_incident": ranking.get("novel_incident"),
            "blocked_by_guardrails": ranking["blocked_by_guardrails"], "excluded_strategies": sorted(excluded),
            "llm_synthesis": synth, "llm_validation": check,
            "strategy_panel": sidx.panel(fam), "novelty": bundle.novelty, "evidence_chain": chain,
            "mode_labels": self._mode(bundle), "timings_ms": bundle.timer.timings_ms,
        })

    # ------------------------------------------------------------------ troubleshooting
    def troubleshoot(self, req) -> dict:
        ts = self.agents.troubleshooting
        with self.rt.lock:
            if req.action == "state":
                return _jsonable({"session": ts.view(req.session_id), "agent_messages": []})
            if req.action == "start":
                if not req.text:
                    raise ValueError("text is required to start a session")
                state = self.agents.start_session(req.text, incident_id=req.incident_id, hints=req.hints)
            elif req.action == "respond":
                state = self.agents.turn({"kind": "respond", "session_id": req.session_id, "attempt_id": req.attempt_id,
                                          "response": req.response, "notes": req.notes})
            elif req.action == "clarify":
                state = self.agents.turn({"kind": "clarify", "session_id": req.session_id, "answer": req.answer,
                                          "declined": req.declined})
            else:
                state = self.agents.turn({"kind": "escalate", "session_id": req.session_id,
                                          "reason": req.reason or "requested by engineer"})
        return _jsonable({"session": state["session"], "agent_messages": state.get("messages", [])})

    def attempts(self, incident_id: str) -> list[dict]:
        return AttemptTracker().for_incident(incident_id)

    # ------------------------------------------------------------------ escalation
    def escalate(self, req) -> dict:
        if req.session_id:
            with self.rt.lock:
                state = self.agents.turn({"kind": "escalate", "session_id": req.session_id, "reason": req.reason})
            return _jsonable({"packet": state["session"].get("escalation"), "session": state["session"],
                              "agent_messages": state.get("messages", [])})
        text = req.text
        if not text and req.incident_id:
            row = incident_row(req.incident_id)
            text = (row or {}).get("description")
        if not text:
            raise ValueError("provide session_id, incident_id or text")
        state = self.agents.escalate(text, req.incident_id, req.reason, hints=req.hints,
                                     fields=req.fields.model_dump() if req.fields else None)
        return _jsonable({"packet": state["escalation"], "agent_messages": state.get("messages", [])})

    # ------------------------------------------------------------------ escalation response (L2/L3)
    def _next_tier(self, tier: str) -> str | None:
        tiers = self.rt.s.tiers
        return tiers[tiers.index(tier) + 1] if tier in tiers and tiers.index(tier) + 1 < len(tiers) else None

    def _escalation_item(self, esc: EscalationRecord, res: EscalationResolution | None,
                         out: EscalationHandoff | None = None, into: EscalationHandoff | None = None) -> dict:
        """status: open (waiting for this tier) | handed_off (this tier passed it up) | resolved."""
        status = "resolved" if res else ("handed_off" if out else "open")
        return {"escalation_id": esc.id, "incident_id": esc.incident_id, "session_id": esc.session_id,
                "tier": esc.tier, "team": esc.team, "expertise": esc.expertise, "reason": esc.reason,
                "escalated_at": esc.created_at.isoformat(), "status": status,
                "next_tier": self._next_tier(esc.tier) if status == "open" else None,
                "packet": esc.packet,
                "handed_off_to": None if out is None else {
                    "escalation_id": out.to_escalation_id, "tier": out.to_tier, "note": out.note,
                    "at": out.created_at.isoformat()},
                "handed_off_from": None if into is None else {
                    "escalation_id": into.from_escalation_id, "tier": into.from_tier, "note": into.note,
                    "at": into.created_at.isoformat()},
                "resolution": None if res is None else {
                    "resolved_by": res.resolved_by, "resolution_notes": res.resolution_notes,
                    "root_cause": res.root_cause, "kb_status": res.kb_status,
                    "resolved_at": res.resolved_at.isoformat()}}

    def escalations(self) -> dict:
        """Every persisted escalation: open first, then handed-off, then resolved; newest first within each."""
        with session_scope() as s:
            rows = s.execute(select(EscalationRecord, EscalationResolution).outerjoin(
                EscalationResolution, EscalationResolution.escalation_id == EscalationRecord.id)
                .order_by(EscalationRecord.created_at.desc())).all()
            hands = s.execute(select(EscalationHandoff)).scalars().all()
            out_of = {h.from_escalation_id: h for h in hands}
            into = {h.to_escalation_id: h for h in hands}
            items = [self._escalation_item(e, r, out_of.get(e.id), into.get(e.id)) for e, r in rows]
        rank = {"open": 0, "handed_off": 1, "resolved": 2}
        items.sort(key=lambda i: rank[i["status"]])  # stable sort keeps newest first inside each group
        return _jsonable({"open": sum(i["status"] == "open" for i in items), "escalations": items})

    def hand_off_escalation(self, escalation_id: int, req) -> dict:
        """The current tier could not fix it and passes it up (L2 → L3). The old escalation stays as history
        and a new open one is created for the next tier, carrying the packet plus what this tier tried."""
        note = req.note.strip()
        with session_scope() as s:
            esc = s.get(EscalationRecord, escalation_id)
            if esc is None:
                raise KeyError(f"escalation {escalation_id}")
            if s.get(EscalationResolution, escalation_id) is not None:
                raise ValueError(f"escalation {escalation_id} is already resolved")
            if s.get(EscalationHandoff, escalation_id) is not None:
                raise ValueError(f"escalation {escalation_id} was already handed off")
            to_tier = self._next_tier(esc.tier)
            if to_tier is None:
                raise ValueError(f"{esc.tier} is the last tier ({' → '.join(self.rt.s.tiers)}); record the fix instead")
            packet = {**(esc.packet or {}), "packet_id": f"ESC-{uuid.uuid4().hex[:8]}",
                      "created_at": datetime.utcnow().isoformat(), "tier": to_tier,
                      "tier_reasons": [f"handed off by {esc.tier}: {note}", *(esc.packet or {}).get("tier_reasons", [])],
                      "handed_off_from": {"escalation_id": esc.id, "tier": esc.tier, "team": esc.team, "note": note}}
            new = EscalationRecord(incident_id=esc.incident_id, session_id=esc.session_id, tier=to_tier, team=esc.team,
                                   expertise=esc.expertise, reason=f"{esc.tier} could not resolve it: {note}", packet=packet)
            s.add(new)
            s.flush()
            hand = EscalationHandoff(from_escalation_id=esc.id, to_escalation_id=new.id, incident_id=esc.incident_id,
                                     from_tier=esc.tier, to_tier=to_tier, note=note)
            s.add(hand)
            s.flush()
            item = self._escalation_item(new, None, None, hand)
            previous = self._escalation_item(esc, None, hand, None)
        return _jsonable({"escalation": item, "previous": previous})

    def resolve_escalation(self, escalation_id: int, req) -> dict:
        """The next tier records what fixed an escalated incident. A live incident is marked resolved
        with those notes, so it enters the same KB evolution loop as a fix found in troubleshooting
        (quality check → indexed, or manual review)."""
        notes = req.resolution_notes.strip()
        root_cause = (req.root_cause or "").strip() or None
        with session_scope() as s:
            esc = s.get(EscalationRecord, escalation_id)
            if esc is None:
                raise KeyError(f"escalation {escalation_id}")
            if s.get(EscalationResolution, escalation_id) is not None:
                raise ValueError(f"escalation {escalation_id} is already resolved")
            iid, session_id, by = esc.incident_id, esc.session_id, f"{esc.tier}, {esc.team}"
            s.add(EscalationResolution(escalation_id=escalation_id, incident_id=iid, resolved_by=by,
                                       resolution_notes=notes, root_cause=root_cause))
        kb = None
        row = incident_row(iid)
        with self.rt.lock:
            if session_id:
                try:
                    self.agents.troubleshooting.record_escalation_resolution(session_id, {
                        "resolved_by": by, "resolution_notes": notes, "root_cause": root_cause,
                        "resolved_at": datetime.utcnow().isoformat()})
                except KeyError:
                    pass  # the session was removed; the escalation record still carries the resolution
            if row and row.get("origin") == "live":
                full = notes + (f" Root cause: {root_cause.rstrip('.')}." if root_cause else "")
                update_incident(iid, status="Resolved", resolved_time=datetime.utcnow(), resolution_notes=full)
                if req.feed_to_kb and not row.get("in_kb"):
                    try:
                        kb = self.evolution.process(iid)
                    except Exception as exc:  # the nightly batch picks the resolved incident up again
                        kb = {"incident_id": iid, "status": "pending_batch", "note": f"KB update deferred: {exc}"}
        with session_scope() as s:
            res = s.get(EscalationResolution, escalation_id)
            res.kb_status = kb["status"] if kb else None
            item = self._escalation_item(s.get(EscalationRecord, escalation_id), res,
                                         into=s.execute(select(EscalationHandoff).where(
                                             EscalationHandoff.to_escalation_id == escalation_id)).scalars().first())
        return _jsonable({"escalation": item, "kb_update": kb})

    # ------------------------------------------------------------------ feedback + KB evolution
    def feedback(self, req) -> dict:
        with session_scope() as s:
            s.add(IncidentFeedback(incident_id=req.incident_id, session_id=req.session_id, helpful=req.helpful,
                                   reasons=list(req.reasons), root_cause_correct=req.root_cause_correct,
                                   pattern_correct=req.pattern_correct,
                                   troubleshooting_resolved=req.troubleshooting_resolved,
                                   escalation_appropriate=req.escalation_appropriate, comment=req.comment,
                                   rating=req.rating))
        out = {"recorded": True, "resolved_percent": None if req.rating is None else resolved_percent(req.rating), "penalised_records": [], "influence_changes": [], "kb_update": None}
        negative = {"wrong resolution", "outdated", "wrong incident"} & set(req.reasons)
        if (req.helpful is False or negative) and req.supporting_incident_ids:
            with self.rt.lock:
                changes = self.evolution.apply_feedback_penalty(
                    req.supporting_incident_ids, next(iter(negative), "not helpful"))
            out["influence_changes"] = changes
            out["penalised_records"] = [c["incident_id"] for c in changes]
        row = incident_row(req.incident_id)
        if req.process_kb_update and row and row.get("origin") == "live" and row.get("status") == "Resolved":
            with self.rt.lock:
                out["kb_update"] = self.evolution.process(req.incident_id)
        out["summary"] = self.feedback_summary()
        return _jsonable(out)

    def feedback_summary(self) -> dict:
        """Star ratings turned into 'how much was resolved': rating / 5, averaged over every rated incident."""
        with session_scope() as s:
            rows = s.execute(select(IncidentFeedback.incident_id, IncidentFeedback.rating,
                                    IncidentFeedback.created_at).where(IncidentFeedback.rating.is_not(None))
                             .order_by(IncidentFeedback.created_at.desc())).all()
        ratings = [r.rating for r in rows]
        n = len(ratings)
        return _jsonable({
            "rated": n,
            "average_rating": round(sum(ratings) / n, 2) if n else None,
            "resolved_percent": resolved_percent(sum(ratings) / n) if n else None,
            "fully_resolved": sum(r == 5 for r in ratings),
            "distribution": {str(k): sum(r == k for r in ratings) for k in range(1, 6)},
            "recent": [{"incident_id": r.incident_id, "rating": r.rating, "resolved_percent": resolved_percent(r.rating),
                        "at": r.created_at.isoformat()} for r in rows[:5]],
            "basis": "each rating counts as rating / 5 resolved (5 stars = 100%, 1 star = 20%); the figure is the mean",
        })

    def add_escalation_info(self, req) -> dict:
        """The reporter adds context after (or while) escalating. It is appended to the escalation packet, so the
        L2/L3 engineer reads it with everything else, and it travels with a hand-off to the next tier."""
        text = req.info.strip()
        with session_scope() as s:
            q = select(EscalationRecord)
            if req.escalation_id is not None:
                q = q.where(EscalationRecord.id == req.escalation_id)
            elif req.session_id:
                q = q.where(EscalationRecord.session_id == req.session_id)
            else:
                raise ValueError("provide escalation_id or session_id")
            esc = s.execute(q.order_by(EscalationRecord.id.desc())).scalars().first()
            if esc is None:
                raise KeyError("no escalation found for that session: escalate first")
            if s.get(EscalationResolution, esc.id) is not None:
                raise ValueError(f"escalation {esc.id} is already resolved")
            note = {"at": datetime.utcnow().isoformat(), "by": req.author or "reporter", "text": text}
            esc.packet = {**(esc.packet or {}), "additional_info": [*(esc.packet or {}).get("additional_info", []), note]}
            esc_id, session_id, packet = esc.id, esc.session_id, esc.packet
        if session_id:
            try:
                self.agents.troubleshooting.add_escalation_note(session_id, note)
            except KeyError:
                pass  # the packet still carries it
        return _jsonable({"escalation_id": esc_id, "additional_info": packet["additional_info"]})

    def postmortem(self, incident_id: str, feed_to_kb: bool = True) -> dict:
        content = pm_service.generate(self.rt, incident_id, self.agents.sidx)
        kb = None
        row = incident_row(incident_id)
        if feed_to_kb and row and row.get("origin") == "live" and row.get("status") == "Resolved" and not row.get("in_kb"):
            with self.rt.lock:
                kb = self.evolution.process(incident_id)
        return _jsonable({"postmortem": content, "kb_update": kb})

    def kb_evolve(self) -> dict:
        with self.rt.lock:
            return _jsonable(self.evolution.run_batch())

    def kb_review(self, incident_id: str, approve: bool, reviewer: str) -> dict:
        with self.rt.lock:
            return _jsonable(self.evolution.review(incident_id, approve, reviewer))

    def kb_quality(self) -> dict:
        rec = self.rt.store.records
        flags: dict[str, int] = {}
        for fl in rec["quality_flags"]:
            for f in list(fl):
                flags[f] = flags.get(f, 0) + 1
        tiers = rec["quality_tier"].value_counts().to_dict()
        worst = rec.nsmallest(15, "quality_score")[["incident_id", "title", "resolution_notes", "quality_score",
                                                    "quality_tier", "quality_flags", "description_source"]]
        prov = rec["description_source"].value_counts().to_dict()
        return _jsonable({"records": int(len(rec)), "tiers": tiers, "flag_counts": flags,
                          "text_provenance": prov, "lowest_quality": worst.to_dict(orient="records"),
                          "threshold": self.rt.s.kb_quality_threshold,
                          "score_histogram": rec["quality_score"].round(1).value_counts().sort_index().to_dict()})

    def kb_evolution_view(self) -> dict:
        with session_scope() as s:
            events = s.execute(select(KBEvolutionEvent).order_by(KBEvolutionEvent.created_at.desc()).limit(80)).scalars().all()
            added = s.execute(select(Incident, KnowledgeQuality).join(
                KnowledgeQuality, KnowledgeQuality.incident_id == Incident.incident_id).where(
                Incident.origin.in_(["kb_evolution", "live"]))).all()
            ev = [{"incident_id": e.incident_id, "stage": e.stage, "status": e.status, "details": e.details,
                   "at": e.created_at.isoformat()} for e in events]
            gate_counts = dict(s.execute(select(KBEvolutionEvent.status, func.count()).where(
                KBEvolutionEvent.stage == "quality_rescored").group_by(KBEvolutionEvent.status)).all())
            recs = [{"incident_id": i.incident_id, "title": i.title, "resolution_notes": i.resolution_notes,
                     "family_id": i.family_id, "in_kb": i.in_kb, "provenance": i.provenance, "quality": q.score,
                     "tier": q.tier, "flags": q.flags, "review_status": q.review_status,
                     "added_at": q.updated_at.isoformat() if q.updated_at else None} for i, q in added]
        return _jsonable({"events": ev, "recently_added": [r for r in recs if r["in_kb"]],
                          "pending_review": [r for r in recs if r["review_status"] == "pending_review"],
                          "quality_threshold": self.evolution.threshold,
                          "gate": {"passed": gate_counts.get("pass", 0), "held": gate_counts.get("below_threshold", 0),
                                   "rejected": sum(r["review_status"] == "rejected" for r in recs)},
                          "pending_candidates": self.evolution.pending_candidates(),
                          "mode": "on-demand per resolved incident + documented nightly batch (scripts/kb_evolution_batch.py)"})

    # ------------------------------------------------------------------ incidents / evidence
    def _historical_row(self, incident_id: str) -> tuple[dict, dict | None] | None:
        """A historical knowledge-base incident lives in the in-memory store, not in the SQL `incidents`
        table (that only holds live and evolved incidents), so the nearest-incident links need this path."""
        if self.rt.store.get(incident_id) is None:
            return None
        rec = self.rt.store.get(incident_id)
        meta = self.rt.store.metadata_view(incident_id)
        fp = self.rt.patterns.fingerprint_of(incident_id)
        row = {"incident_id": incident_id, "title": rec.get("title"), "description": rec.get("description"),
               "status": meta.get("status"), "priority": meta.get("priority"), "open_time": meta.get("open_time"),
               "impact_scope": meta.get("impact_scope"), "origin": "historical"}
        return row, (fp.values if fp else None)

    def incident(self, incident_id: str) -> dict | None:
        row = incident_row(incident_id)
        if row is None:
            hist = self._historical_row(incident_id)
            if hist is None:
                return None
            row, fp_values = hist
            fam = self.rt.patterns.family_of(incident_id)
            return _jsonable({"incident": row, "fingerprint": fp_values, "knowledge_quality": None,
                              "family": fam.summary() if fam else None,
                              "causal_chain": self.agents.pattern_agent.causal_chain(incident_id),
                              "strategy_key": self.agents.sidx.strategy_of.get(incident_id), "escalations": []})
        with session_scope() as s:
            fp = s.get(IncidentFingerprint, incident_id)
            kq = s.get(KnowledgeQuality, incident_id)
            fpd = None if fp is None else {c.name: getattr(fp, c.name) for c in IncidentFingerprint.__table__.columns}
            kqd = None if kq is None else {"score": kq.score, "tier": kq.tier, "flags": kq.flags,
                                           "components": kq.components, "review_status": kq.review_status}
            escs = s.execute(select(EscalationRecord).where(EscalationRecord.incident_id == incident_id)).scalars().all()
        fam = self.rt.patterns.family_of(incident_id)
        row.pop("ground_truth", None)
        return _jsonable({"incident": row, "fingerprint": fpd, "knowledge_quality": kqd,
                          "family": fam.summary() if fam else None,
                          "causal_chain": self.agents.pattern_agent.causal_chain(incident_id),
                          "strategy_key": self.agents.sidx.strategy_of.get(incident_id),
                          "escalations": [{"tier": e.tier, "team": e.team, "reason": e.reason,
                                           "at": e.created_at.isoformat()} for e in escs]})

    def evidence_chain(self, incident_id: str) -> dict | None:
        if incident_id in self._evidence_cache:
            return {"incident_id": incident_id, "source": "latest analysis of this incident",
                    "evidence_chain": self._evidence_cache[incident_id]}
        row = incident_row(incident_id)
        if row is None:
            return None
        text = f"{row.get('title') or ''}. {row.get('description') or ''}".strip(". ")
        if not text:
            return {"incident_id": incident_id, "evidence_chain": None,
                    "note": "this incident has no description text (structured-only record) — insufficient evidence"}
        bundle = analyze_text(self.rt, text, exclude_ids=[incident_id], top_k=10)
        ranking = rank_resolutions(bundle.retrieval.results, self.agents.sidx, reranked=bundle.retrieval.mode.reranked,
                                   family=bundle.families[0] if bundle.families else None)
        chain = assemble(self.rt, bundle, ranking, subject=f"historical incident {incident_id} (leave-one-out)")
        return _jsonable({"incident_id": incident_id,
                          "source": "recomputed with the incident itself excluded from retrieval",
                          "evidence_chain": chain})

    # ------------------------------------------------------------------ patterns
    def patterns(self, include_emerging: bool = True) -> dict:
        fams = [f.summary() | {"n_strategies": f.extra.get("n_strategies"),
                               "recurrence_finding": f.extra.get("recurrence", {}).get("finding")}
                for f in self.rt.patterns.families.values() if include_emerging or f.status == "active"]
        proactive = json.loads((self.rt.s.processed_dir / "proactive.json").read_text(encoding="utf-8"))
        return _jsonable({"families": sorted(fams, key=lambda f: -f["size"]), "meta": self.rt.patterns.meta,
                          "cross_symptom_findings": [f for f in fams if f.get("cross_symptom")],
                          "proactive": proactive})

    def pattern(self, pattern_id: str) -> dict | None:
        fam = self.rt.patterns.families.get(pattern_id)
        if fam is None:
            return None
        members = [self.rt.store.get(m) for m in fam.members[:25] if self.rt.store.get(m)]
        graph = json.loads((self.rt.s.processed_dir / "family_graph.json").read_text(encoding="utf-8"))
        links = [l for l in graph["links"] if l["source"] == pattern_id or l["target"] == pattern_id]
        return _jsonable({
            **fam.summary(), "causal_chain": fam.extra.get("causal_chain"), "recurrence": fam.extra.get("recurrence"),
            "strategies": self.agents.sidx.panel(pattern_id),
            "members_sample": [{k: m.get(k) for k in ("incident_id", "title", "description", "resolution_notes",
                                                      "open_time", "ci_name", "description_source", "quality_tier")}
                               for m in members],
            "example_causal_chains": [self.agents.pattern_agent.causal_chain(m) for m in fam.members[:3]],
            "graph_links": links,
        })

    def family_graph(self) -> dict:
        return json.loads((self.rt.s.processed_dir / "family_graph.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ correlation
    def simulate(self, req) -> dict:
        corr = self.rt.correlator
        if req.reset:
            corr.reset()
        start = datetime.fromisoformat(req.start_at) if req.start_at else datetime.utcnow()
        if req.texts:
            items = [(i * req.interval_minutes, t) for i, t in enumerate(req.texts)]
            tag = "custom"
        else:
            items = PRESETS[req.preset]
            tag = req.preset
        results = []
        for offset, text in items:
            iid = create_live_incident(text, title=f"[simulated] {text[:60]}")
            results.append(corr.ingest(text, received_at=start + timedelta(minutes=offset), incident_id=iid,
                                       scenario_tag=tag))
        alerts = {r["alert"]["alert_id"]: r["alert"] for r in results if r["alert"]}
        return _jsonable({"ingested": results, "alerts": list(alerts.values()), "snapshot": corr.snapshot()})

    def correlations(self) -> dict:
        snap = self.rt.correlator.snapshot()
        with session_scope() as s:
            n = s.execute(select(func.count()).select_from(CorrelationAlert)).scalar()
        snap["alerts_persisted_total"] = n
        return _jsonable(snap)

    # ------------------------------------------------------------------ health
    def health(self) -> dict:
        rt = self.rt
        ok_vec, vec_msg = rt.vectors.healthy()
        from backend.config.settings import calibration_available
        return {
            "status": "ok",
            "llm": rt.llm.status() | {"mode": "full" if rt.llm.available else RETRIEVAL_ONLY_LABEL},
            "embeddings": {"provider": rt.embedder.name, "requested": rt.embedder.requested,
                           "fallback_reason": rt.embedder.fallback_reason},
            "reranker": {"provider": rt.reranker.name, "fallback_reason": rt.reranker.fallback_reason},
            "vector_store": {"ok": ok_vec, "detail": vec_msg,
                             "label": None if ok_vec else "keyword-only (semantic search unavailable)"},
            "knowledge_base": {"records": len(rt.store), "families": len(rt.patterns.families)},
            "calibration": {"cross_encoder": calibration_available("ce_platt_a"),
                            "novelty": rt.novelty.calibrated},
            "triage_models": rt.outcome_models.available,
            "escalation_tiers": rt.s.tiers,
        }


def _closure_class_for(top: dict, sidx) -> str:
    """Closure class of the recommended strategy = the class of its dominant REAL closure code."""
    from backend.data_pipeline.cleaning import closure_class

    strat = sidx.by_key.get(top.get("strategy_key")) if sidx else None
    codes = (strat or {}).get("closure_codes") or {}
    return closure_class(max(codes, key=codes.get)) if codes else "unspecified"


_platform: Platform | None = None
_plock = threading.Lock()


def get_platform() -> Platform:
    global _platform
    with _plock:
        if _platform is None:
            _platform = Platform()
        return _platform


def set_platform(p: Platform | None) -> None:
    global _platform
    with _plock:
        _platform = p
