"""Interactive troubleshooting ("Have you tried this?") with formal attempt tracking.

Flow per session:
  start → analysis → [clarification? (trigger 1/2)] → step 1 (top-ranked resolution)
  FAILED  → strategy excluded → secondary retrieval without it → next-best step
  UNKNOWN → step skipped for the next pick (not permanently excluded)
  WORKED  → resolved → hand-off to KB evolution (feedback + postmortem)
  round cap reached (or no further evidence-backed step) → pre-escalation clarification check →
      answer → one more targeted step; declined / not useful → escalation packet
  escalated → the next tier records what fixed it (Platform.resolve_escalation) → KB evolution

Sequence mining: the datasets contain no sequential-attempt log (verified in Phase 1), so the next
step always comes from secondary retrieval that filters out failed approaches — never from a
mined "step 2 usually follows step 1" sequence.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from backend.database.session import session_scope
from backend.models.entities import TroubleshootingSession
from backend.rag.llm import RETRIEVAL_ONLY_LABEL
from backend.rag.resolution import rank_resolutions
from backend.rag.strategy import normalized_action
from backend.services.analysis import analyze_text
from backend.services.incidents import create_live_incident, update_incident
from backend.troubleshooting.attempts import AttemptTracker
from backend.troubleshooting.clarification import ClarificationPolicy, parse_answer

SIMILAR_STEP_THRESHOLD = 0.5  # masked action-clause cosine: restart variants score 0.68-0.73, different actions < 0.15


class TroubleshootingService:
    def __init__(self, rt, sidx, escalation_builder=None):
        self.rt = rt
        self.sidx = sidx
        self.attempts = AttemptTracker()
        self.policy = ClarificationPolicy(rt.s.clarification_confidence_threshold, rt.s.clarification_family_margin,
                                          rt.s.max_clarifications_per_session)
        self.escalation_builder = escalation_builder
        self.max_rounds = rt.s.troubleshooting_max_rounds

    # ------------------------------------------------------------------ persistence helpers
    def _load(self, session_id: str) -> TroubleshootingSession:
        if not session_id:
            raise KeyError(session_id)
        with session_scope() as s:
            sess = s.get(TroubleshootingSession, session_id)
            if sess is None:
                raise KeyError(session_id)
            s.expunge(sess)
            return sess

    def _save(self, sess: TroubleshootingSession) -> None:
        state = json.loads(json.dumps(sess.state, default=str))  # fresh object → JSON change is detected
        with session_scope() as s:
            row = s.get(TroubleshootingSession, sess.session_id)
            if row is None:
                s.add(TroubleshootingSession(session_id=sess.session_id, incident_id=sess.incident_id,
                                             status=sess.status, round=sess.round, query_text=sess.query_text,
                                             state=state))
            else:
                row.status, row.round, row.state = sess.status, sess.round, state
                row.updated_at = datetime.utcnow()

    @staticmethod
    def _event(state: dict, kind: str, **data) -> None:
        state.setdefault("events", []).append({"at": datetime.utcnow().isoformat(), "kind": kind, **data})

    # ------------------------------------------------------------------ analysis for the session
    def _analyze(self, sess: TroubleshootingSession):
        st = sess.state
        excluded = set(st.get("excluded_strategies", [])) | set(st.get("skip_once", []))
        sidx = self.sidx

        def exclude_fn(rec):
            return rec is not None and sidx.key_for(rec["incident_id"]) in excluded

        bundle = analyze_text(self.rt, sess.query_text, hints=st.get("hints", {}), top_k=20,
                              exclude_ids=st.get("exclude_ids") or None,
                              exclude_fn=exclude_fn if excluded else None)
        fam = bundle.families[0] if bundle.families else None
        ranking = rank_resolutions(bundle.retrieval.results, sidx, excluded, bundle.retrieval.mode.reranked, family=fam)
        ranking = self._drop_similar_to_failed(ranking, st.get("failed_steps", []))
        st["family"] = bundle.families[0] if bundle.families else None
        st["fingerprint"] = bundle.fingerprint.as_dict()
        st["novelty"] = bundle.novelty
        st["mode_labels"] = list(bundle.retrieval.mode.labels) + ([] if self.rt.llm.available else [RETRIEVAL_ONLY_LABEL])
        st["last_top_retrieved"] = [r.incident_id for r in bundle.retrieval.results[:5]]
        return bundle, ranking

    def _drop_similar_to_failed(self, ranking: dict, failed_steps: list[str]) -> dict:
        """A different strategy key can still describe the same action (e.g. two phrasings of
        'restart the service'). Steps whose text is near-identical to a failed step are skipped."""
        if not failed_steps or not ranking["top"]:
            return ranking
        cands = [ranking["top"]] + ranking["alternatives"]
        fv = self.rt.embedder.embed(failed_steps)
        cv = self.rt.embedder.embed([normalized_action(c["step"]) for c in cands])
        keep, dropped = [], []
        for c, sims in zip(cands, cv @ fv.T):
            (dropped if float(sims.max()) >= SIMILAR_STEP_THRESHOLD else keep).append(c)
        ranking = dict(ranking)
        ranking["top"], ranking["alternatives"] = (keep[0] if keep else None), keep[1:]
        ranking["dropped_as_similar_to_failed"] = [c["strategy_key"] for c in dropped]
        return ranking

    # ------------------------------------------------------------------ API
    def start(self, text: str, incident_id: str | None = None, hints: dict | None = None,
              exclude_ids: list[str] | None = None) -> dict:
        iid = incident_id or create_live_incident(text)
        sess = TroubleshootingSession(session_id=f"TS-{uuid.uuid4().hex[:10]}", incident_id=iid, status="active",
                                      round=0, query_text=text,
                                      state={"hints": dict(hints or {}), "excluded_strategies": [], "skip_once": [],
                                             "clarifications": [], "events": [],
                                             "exclude_ids": list(exclude_ids or [])})
        self._event(sess.state, "session_started", text=text)
        bundle, ranking = self._analyze(sess)
        if bundle.novelty.get("is_novel"):
            sess.status = "novel"
            self._event(sess.state, "novel_incident", verdict=bundle.novelty["verdict"],
                        known_probability=bundle.novelty.get("known_probability"))
            self._save(sess)
            return self.view(sess.session_id, extra={"note": "No sufficiently similar historical incident — route to "
                                                             "fresh investigation (escalation packet available)."})
        top_conf = ranking["top"]["confidence"] if ranking["top"] else None
        q = self.policy.check(top_confidence=top_conf, is_vague=bundle.qu.is_vague, families=bundle.families,
                              fingerprint_values=bundle.fingerprint.values, answered=sess.state["hints"],
                              asked_count=len(sess.state["clarifications"]))
        if q:
            return self._ask(sess, q)
        return self._next_step(sess, ranking)

    def respond(self, session_id: str, attempt_id: str, response: str, notes: str | None = None) -> dict:
        sess = self._load(session_id)
        if sess.status not in ("active",):
            raise ValueError(f"session is {sess.status}; no step awaiting a response")
        att = self.attempts.respond(attempt_id, response, notes)
        st = sess.state
        self._event(st, "attempt_response", attempt_id=attempt_id, response=att["engineer_response"],
                    strategy_key=att["strategy_key"])
        if att["engineer_response"] == "WORKED":
            sess.status = "resolved"
            st["resolved_by"] = att
            update_incident(sess.incident_id, status="Resolved", resolved_time=datetime.utcnow(),
                            resolution_notes=f"{att['step_description']}. {att.get('notes') or ''}".strip())
            self._event(st, "resolved", attempt_id=attempt_id)
            self._save(sess)
            return self.view(session_id)
        if att["engineer_response"] == "FAILED":
            st["excluded_strategies"] = sorted(set(st["excluded_strategies"]) | {att["strategy_key"]})
            cur = st.get("current") or {}
            st.setdefault("failed_steps", []).append(normalized_action(cur.get("step") or att["step_description"]))
            st["skip_once"] = []
        else:  # UNKNOWN — skip for the next pick only
            st["skip_once"] = [att["strategy_key"]]
        if sess.round >= self.max_rounds:
            return self._pre_escalation(sess, reason=f"round cap ({self.max_rounds}) reached")
        bundle, ranking = self._analyze(sess)
        if ranking["top"] is None:
            return self._pre_escalation(sess, reason="no further evidence-backed step after excluding failed approaches",
                                        bundle=bundle)
        return self._next_step(sess, ranking)

    def clarify(self, session_id: str, answer: str | None = None, declined: bool = False) -> dict:
        sess = self._load(session_id)
        if sess.status != "awaiting_clarification":
            raise ValueError("no clarifying question is pending for this session")
        st = sess.state
        pending = st["clarifications"][-1]
        value = None if declined else parse_answer(pending["field"], answer or "")
        pending.update({"answer": answer, "declined": declined, "parsed_value": value,
                        "answered_at": datetime.utcnow().isoformat()})
        if value:
            st["hints"][pending["field"]] = value
            pending["learned"] = f"{pending['field']} = {value}"
        else:
            pending["learned"] = "nothing (declined or not understood)"
        self._event(st, "clarification_answered", field=pending["field"], value=value, declined=declined)
        sess.status = "active"
        if pending["trigger"] == "pre_escalation":
            if not value:
                return self._escalate(sess, reason="clarification declined / not informative after round cap")
            st["bonus_round"] = True
            bundle, ranking = self._analyze(sess)
            if ranking["top"] is None:
                return self._escalate(sess, reason="clarification did not surface a new evidence-backed step")
            return self._next_step(sess, ranking)
        bundle, ranking = self._analyze(sess)
        if bundle.novelty.get("is_novel"):
            sess.status = "novel"
            self._save(sess)
            return self.view(session_id)
        return self._next_step(sess, ranking)

    def escalate(self, session_id: str, reason: str = "requested by engineer") -> dict:
        sess = self._load(session_id)
        if sess.status == "escalated":
            return self.view(session_id)
        return self._escalate(sess, reason=reason)

    # ------------------------------------------------------------------ internals
    def _ask(self, sess, q) -> dict:
        sess.status = "awaiting_clarification"
        sess.state["clarifications"].append({**q.as_dict(), "asked_at": datetime.utcnow().isoformat(),
                                             "at_round": sess.round})
        self._event(sess.state, "clarification_asked", field=q.field, trigger=q.trigger)
        self._save(sess)
        return self.view(sess.session_id)

    def _next_step(self, sess, ranking) -> dict:
        top = ranking["top"]
        if top is None:
            return self._escalate(sess, reason="no evidence-backed resolution available")
        sess.round += 1
        att = self.attempts.create(incident_id=sess.incident_id, session_id=sess.session_id, round_no=sess.round, step=top)
        sess.state["current"] = {**{k: top[k] for k in ("strategy_key", "action", "step", "expected_observation",
                                                        "supporting_incidents", "confidence", "confidence_basis",
                                                        "confidence_components", "safety", "kind", "strategy_stats",
                                                        "evidence_provenance")},
                                 "attempt_id": att["attempt_id"], "round": sess.round}
        sess.state["alternatives"] = [{"strategy_key": a["strategy_key"], "action": a["action"],
                                       "confidence": a["confidence"]} for a in ranking["alternatives"][:3]]
        self._event(sess.state, "step_suggested", attempt_id=att["attempt_id"], strategy_key=top["strategy_key"],
                    round=sess.round)
        self._save(sess)
        return self.view(sess.session_id)

    def _pre_escalation(self, sess, reason: str, bundle=None) -> dict:
        st = sess.state
        if st.get("bonus_round"):
            return self._escalate(sess, reason=f"{reason}; the post-clarification step also failed")
        fp_values = st.get("fingerprint", {}).get("values", {})
        q = self.policy.check(top_confidence=None, is_vague=False, families=[], fingerprint_values=fp_values,
                              answered=st.get("hints", {}), asked_count=len(st["clarifications"]), about_to_escalate=True)
        if q:
            self._event(st, "pre_escalation_check", reason=reason, outcome="asking one clarifying question")
            return self._ask(sess, q)
        self._event(st, "pre_escalation_check", reason=reason, outcome="no useful clarification available")
        return self._escalate(sess, reason=reason)

    def _escalate(self, sess, reason: str) -> dict:
        """Hand-off to the Escalation Agent. Inside the agent graph the session is marked
        `escalation_requested` and the Escalation Agent node builds the packet; when the service is
        used directly (tests), an injected `escalation_builder` finalises immediately."""
        sess.state["escalation_reason"] = reason
        if self.escalation_builder is None:
            sess.status = "escalation_requested"
            self._event(sess.state, "escalation_requested", reason=reason)
            self._save(sess)
            return self.view(sess.session_id)
        packet = self.escalation_builder(sess, reason)
        sess.status = "escalated"
        sess.state["escalation"] = packet
        self._event(sess.state, "escalated", reason=reason, tier=packet.get("tier"))
        self._save(sess)
        return self.view(sess.session_id)

    def finalize_escalation(self, session_id: str, packet: dict) -> dict:
        sess = self._load(session_id)
        sess.status = "escalated"
        sess.state["escalation"] = packet
        self._event(sess.state, "escalated", reason=packet.get("reason"), tier=packet.get("tier"))
        self._save(sess)
        return self.view(session_id)

    def record_escalation_resolution(self, session_id: str, resolution: dict) -> None:
        """The next tier closed the escalation. The session keeps status 'escalated' (that is what
        happened in it); the resolution is attached so the session view can show how it ended."""
        sess = self._load(session_id)
        sess.state["escalation_resolution"] = resolution
        self._event(sess.state, "resolved_after_escalation", resolved_by=resolution.get("resolved_by"))
        self._save(sess)

    def session_context(self, session_id: str) -> dict:
        sess = self._load(session_id)
        return {"session_id": sess.session_id, "incident_id": sess.incident_id, "query_text": sess.query_text,
                "status": sess.status, "state": sess.state}

    def view(self, session_id: str, extra: dict | None = None) -> dict:
        sess = self._load(session_id)
        st = sess.state
        pending_q = st["clarifications"][-1] if sess.status == "awaiting_clarification" else None
        return {
            "session_id": sess.session_id, "incident_id": sess.incident_id, "status": sess.status,
            "round": sess.round, "max_rounds": self.max_rounds, "query": sess.query_text,
            "current_step": st.get("current") if sess.status == "active" else None,
            "clarification": pending_q, "clarifications": st["clarifications"],
            "attempts": self.attempts.for_session(session_id),
            "alternatives": st.get("alternatives", []),
            "excluded_strategies": st.get("excluded_strategies", []),
            "family": {k: st["family"][k] for k in ("family_id", "name", "match_strength", "vote_share")} if st.get("family") else None,
            "novelty": st.get("novelty"), "mode_labels": st.get("mode_labels", []),
            "escalation": st.get("escalation"), "escalation_reason": st.get("escalation_reason"),
            "escalation_resolution": st.get("escalation_resolution"),
            "resolved_by": st.get("resolved_by"),
            "events": st.get("events", []), **(extra or {}),
        }
