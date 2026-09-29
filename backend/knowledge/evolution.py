"""Knowledge Base Evolution loop.

    New resolved incident
      → resolution attempt history + final outcome (formal attempt records)
      → engineer feedback (helpful? root cause correct? pattern correct? escalation appropriate?)
      → Knowledge Quality Manager re-scores the candidate record
      → score ≥ KB_QUALITY_THRESHOLD:
            fingerprint → matched to an existing family or spawns an "emerging" one
            → relationship graph updated → embedding added to ChromaDB → BM25 rebuilt
      → score < threshold: flagged for MANUAL REVIEW (not silently discarded, not silently added)

Runs per incident on demand (demo) and as a documented batch (`scripts/kb_evolution_batch.py`,
intended to run nightly with `--loop` or from a scheduler). Every stage is written to
the `kb_evolution_events` audit table. Feedback does NOT retrain any model; it changes knowledge
records (quality, influence weight) — which is exactly what is claimed.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select

from backend.database.session import session_scope
from backend.knowledge.indexer import chunk_metadata
from backend.knowledge.quality import assess_single, mask_entities, resolution_detail
from backend.models.entities import (
    Incident, IncidentFeedback, IncidentFingerprint, IncidentRelationship, KBEvolutionEvent, KnowledgeQuality,
    Postmortem, ResolutionAttempt, TroubleshootingSession,
)

log = logging.getLogger(__name__)
FEEDBACK_PENALTY = 0.15


def _event(s, iid: str, stage: str, status: str, **details) -> None:
    s.add(KBEvolutionEvent(incident_id=iid, stage=stage, status=status, details=json.loads(json.dumps(details, default=str))))


class KBEvolution:
    def __init__(self, rt, sidx=None):
        self.rt = rt
        self.sidx = sidx
        self.threshold = rt.s.kb_quality_threshold

    # ------------------------------------------------------------------ candidate
    def build_candidate(self, incident_id: str) -> dict:
        with session_scope() as s:
            inc = s.get(Incident, incident_id)
            if inc is None:
                raise KeyError(incident_id)
            if inc.status not in ("Resolved", "Closed"):
                raise ValueError(f"incident {incident_id} is not resolved (status={inc.status})")
            atts = s.execute(select(ResolutionAttempt).where(ResolutionAttempt.incident_id == incident_id)
                             .order_by(ResolutionAttempt.timestamp)).scalars().all()
            fb = s.execute(select(IncidentFeedback).where(IncidentFeedback.incident_id == incident_id)
                           .order_by(IncidentFeedback.created_at.desc())).scalars().first()
            pm = s.execute(select(Postmortem).where(Postmortem.incident_id == incident_id)
                           .order_by(Postmortem.created_at.desc())).scalars().first()
            sess = s.execute(select(TroubleshootingSession).where(TroubleshootingSession.incident_id == incident_id)
                             .order_by(TroubleshootingSession.created_at.desc())).scalars().first()
            worked = [a for a in atts if a.engineer_response == "WORKED"]
            failed = [a for a in atts if a.engineer_response == "FAILED"]
            hints = (sess.state or {}).get("hints", {}) if sess else {}
            clar = [c.get("learned") for c in (sess.state or {}).get("clarifications", [])] if sess else []
            engineer_note = None
            if worked and worked[-1].notes and "[engineer]" in worked[-1].notes:
                engineer_note = worked[-1].notes.split("[engineer]", 1)[1].strip()
            if worked:
                fix = worked[-1].step_description
                detail = (worked[-1].notes or "").split("\n[engineer]")[0]
                res = f"{fix}. {detail}".strip()
                if engineer_note:
                    res += f" Engineer note: {engineer_note}"
            else:
                res = inc.resolution_notes or ""
            if pm and pm.content.get("root_cause", {}).get("statement"):
                res += f" Root cause (postmortem): {pm.content['root_cause']['statement']}."
            if failed:
                res += " Previously tried without success: " + "; ".join(a.step_description for a in failed) + "."
            desc = inc.description or ""
            if clar:
                desc += " (" + "; ".join(c for c in clar if c and not c.startswith("nothing")) + ")"
            opened, resolved = inc.open_time, inc.resolved_time or datetime.utcnow()
            return {
                "incident_id": incident_id, "title": inc.title or desc[:80], "description": desc,
                "resolution_notes": res, "source": "kb_evolution", "origin": "kb_evolution",
                "open_time": opened, "resolved_time": resolved,
                "resolution_hours": (resolved - opened).total_seconds() / 3600 if opened else None,
                "priority": inc.priority or "Not Set", "impact": inc.impact or "Not Set", "urgency": inc.urgency or "Not Set",
                "category": inc.category, "ci_name": inc.ci_name, "status": "Resolved",
                "hints": hints, "attempts": [{"step": a.step_description, "response": a.engineer_response,
                                              "strategy_key": a.strategy_key} for a in atts],
                "worked_strategy": worked[-1].strategy_key if worked else None,
                "feedback": None if fb is None else {
                    "helpful": fb.helpful, "reasons": fb.reasons, "root_cause_correct": fb.root_cause_correct,
                    "pattern_correct": fb.pattern_correct, "troubleshooting_resolved": fb.troubleshooting_resolved,
                    "escalation_appropriate": fb.escalation_appropriate},
                "postmortem_id": pm.id if pm else None,
            }

    # ------------------------------------------------------------------ scoring
    def score(self, cand: dict) -> tuple[dict, np.ndarray, np.ndarray]:
        rt = self.rt
        row = pd.Series({
            "resolution_notes": cand["resolution_notes"], "category_conflict": False, "closure_class": None,
            "priority_consistent": None, "reopened": None, "reopened_source": "missing",
            "no_of_reassignments": None,
            **{f"{f}_source": ("original" if cand.get(f) not in (None, "Not Set") else "missing")
               for f in ("impact", "urgency", "priority", "closure_code", "open_time", "resolved_time")},
        })
        desc_m = rt.embedder.embed([mask_entities(f"{cand['title']}. {cand['description']}", cand.get("ci_name"))])[0]
        res_m = rt.embedder.embed([mask_entities(cand["resolution_notes"], cand.get("ci_name"))])[0]
        hits = rt.retriever.search(cand["description"], top_k=10, rerank=False).results
        neigh = [h.resolution_notes for h in hits if resolution_detail(h.resolution_notes)[0] > 0.2][:10]
        neigh_vecs = rt.embedder.embed([mask_entities(n, None) for n in neigh]) if neigh else np.zeros((0, len(res_m)))
        fence = json.loads((rt.s.processed_dir / "embedding_meta.json").read_text())["quality_meta"]["resolution_consistency_fence"]
        q = assess_single(row, desc_m, res_m, neigh_vecs, fence)
        score, flags, comps = q.score, list(q.flags), dict(q.components)
        fb = cand.get("feedback") or {}
        if fb.get("troubleshooting_resolved") or cand.get("worked_strategy"):
            comps["outcome"] = 1.0  # a confirmed working fix is real outcome evidence
        if fb.get("helpful") is False or fb.get("root_cause_correct") is False:
            score -= FEEDBACK_PENALTY
            flags.append("negative_engineer_feedback")
        if fb.get("helpful") is True and fb.get("root_cause_correct") is True:
            comps["feedback_bonus"] = 0.05
            score += 0.05
        score = round(float(min(1.0, max(0.0, score))), 4)
        tier = "high" if score >= 0.7 else ("medium" if score >= 0.5 else "low")
        return {"score": score, "tier": tier, "flags": flags, "components": comps}, desc_m, res_m

    # ------------------------------------------------------------------ pipeline
    def process(self, incident_id: str, force_review: bool = False) -> dict:
        cand = self.build_candidate(incident_id)
        q, desc_m, _ = self.score(cand)
        passed = q["score"] >= self.threshold and not force_review
        with session_scope() as s:
            _event(s, incident_id, "candidate_built", "ok", attempts=len(cand["attempts"]), feedback=cand["feedback"])
            _event(s, incident_id, "quality_rescored", "pass" if passed else "below_threshold",
                   score=q["score"], threshold=self.threshold, flags=q["flags"])
            kq = s.get(KnowledgeQuality, incident_id) or KnowledgeQuality(incident_id=incident_id, score=0, tier="low")
            kq.score, kq.tier, kq.flags, kq.components = q["score"], q["tier"], q["flags"], q["components"]
            kq.dup_group, kq.near_dup_group, kq.canonical = incident_id, incident_id, True
            kq.review_status = "auto" if passed else "pending_review"
            s.merge(kq)
            if not passed:
                _event(s, incident_id, "manual_review", "flagged",
                       reason=f"quality {q['score']} < {self.threshold}" if not force_review else "forced review")
        if not passed:
            return {"incident_id": incident_id, "status": "pending_review", "quality": q,
                    "note": "Below the quality threshold — flagged for manual review, not indexed."}
        return self._index(cand, q)

    def review(self, incident_id: str, approve: bool, reviewer: str = "reviewer") -> dict:
        with session_scope() as s:
            kq = s.get(KnowledgeQuality, incident_id)
            if kq is None or kq.review_status != "pending_review":
                raise ValueError("record is not pending review")
            kq.review_status = "approved" if approve else "rejected"
            _event(s, incident_id, "manual_review", kq.review_status, reviewer=reviewer)
            q = {"score": kq.score, "tier": kq.tier, "flags": kq.flags, "components": kq.components}
        if not approve:
            return {"incident_id": incident_id, "status": "rejected"}
        return self._index(self.build_candidate(incident_id), q, approved=True)

    def _index(self, cand: dict, q: dict, approved: bool = False) -> dict:
        rt = self.rt
        iid = cand["incident_id"]
        fp = rt.fingerprinter.from_query(f"{cand['title']}. {cand['description']} {cand['resolution_notes']}",
                                         hints=cand.get("hints"))
        desc_vec = rt.embedder.embed([f"{cand['title']}. {cand['description']}"])[0]
        fid, created, sim = rt.patterns.assign_new(iid, desc_vec, fp)
        rt.patterns.save(rt.s)
        strategy_key = self._assign_strategy(iid, fid, cand)
        record = self._record(cand, q, fp)
        chunks = rt.store.add_record(record)
        vecs = rt.embedder.embed(chunks["text"].tolist())
        rt.vectors.upsert(chunks["chunk_id"].tolist(), vecs, chunks["text"].tolist(),
                          [chunk_metadata(record, {"quality_score": q["score"], "canonical": True, "dup_group": iid})
                           for _ in range(len(chunks))], rt.embedder.name)
        rt.retriever.rebuild_bm25()
        with session_scope() as s:
            inc = s.get(Incident, iid)
            inc.in_kb, inc.origin, inc.family_id = True, "kb_evolution", fid
            inc.resolution_notes = cand["resolution_notes"]
            inc.provenance = {**(inc.provenance or {}), "resolution_notes": "original", "category": "derived"}
            s.merge(IncidentFingerprint(incident_id=iid, **fp.values, provenance=fp.provenance, extractor_version="rules-v1"))
            if cand.get("ci_name"):
                prev = s.execute(select(Incident).where(Incident.ci_name == cand["ci_name"], Incident.in_kb == True,  # noqa: E712
                                                        Incident.incident_id != iid)
                                 .order_by(Incident.open_time.desc())).scalars().first()
                if prev:
                    s.add(IncidentRelationship(src_id=prev.incident_id, dst_id=iid, rel_type="same_ci", weight=1.0,
                                               tag="observed", evidence={"ci_name": cand["ci_name"]}))
            if cand.get("worked_strategy"):
                s.add(IncidentRelationship(src_id=iid, dst_id=cand["worked_strategy"], rel_type="resolved_by_strategy",
                                           weight=1.0, tag="observed", evidence={"source": "attempt marked WORKED"}))
            _event(s, iid, "fingerprinted", "ok", fingerprint={k: v for k, v in fp.values.items() if v != "Unknown"})
            _event(s, iid, "family_assigned", "new_family" if created else "existing_family", family_id=fid,
                   centroid_similarity=round(sim, 4))
            _event(s, iid, "indexed", "ok", vector_ids=chunks["chunk_id"].tolist(), bm25="rebuilt",
                   strategy_key=strategy_key, approved_by_review=approved)
        return {"incident_id": iid, "status": "added_to_kb", "quality": q, "family_id": fid,
                "family_created": created, "centroid_similarity": round(sim, 4), "strategy_key": strategy_key,
                "retrievable": True}

    def _assign_strategy(self, iid: str, fid: str, cand: dict) -> str:
        sidx = self.sidx
        if sidx is None:
            return f"INC:{iid}"
        strategies = sidx.by_family.get(fid, [])
        if strategies:
            v = self.rt.embedder.embed([mask_entities(cand["resolution_notes"], cand.get("ci_name"))])[0]
            sims = [(float(np.asarray(s_["centroid"]) @ v), s_["strategy_key"]) for s_ in strategies]
            best = max(sims)
            if best[0] >= 0.6:
                sidx.strategy_of[iid] = best[1]
                return best[1]
        return sidx.key_for(iid)

    def _record(self, cand: dict, q: dict, fp) -> dict:
        from backend.config.taxonomy import CATEGORY_TEAM

        comp_cat = {"Database": "Database", "Storage": "Storage", "Network": "Network", "VPN gateway": "Network",
                    "Authentication service": "Security", "TLS certificate": "Security", "Endpoint security": "Security",
                    "Server": "Infrastructure", "End-user device": "Hardware", "Printer": "Hardware",
                    "Banking device": "Hardware"}
        category = cand.get("category") or comp_cat.get(fp.values["component"], "Application")
        rec = {
            "incident_id": cand["incident_id"], "title": cand["title"], "description": cand["description"],
            "resolution_notes": cand["resolution_notes"], "source": "kb_evolution", "category": category,
            "ci_name": cand.get("ci_name") or "Unknown", "ci_group": "other", "ci_subcategory": "Unknown",
            "priority": cand["priority"], "impact": cand["impact"], "urgency": cand["urgency"], "status": "Resolved",
            "severity": "Unknown", "impact_scope": fp.values["impact_scope"], "suggested_team": CATEGORY_TEAM.get(category),
            "open_time": cand["open_time"], "resolved_time": cand["resolved_time"],
            "resolution_hours": cand["resolution_hours"], "reopened": None, "no_of_reassignments": None,
            "related_change": None, "kb_number": None, "text_generator": "engineer", "closure_code": "Not Set",
            "closure_class": "Unknown",
            "title_source": "original", "description_source": "original", "resolution_notes_source": "original",
            "category_source": "derived", "priority_source": "original" if cand["priority"] != "Not Set" else "missing",
            "impact_source": "original" if cand["impact"] != "Not Set" else "missing",
            "urgency_source": "original" if cand["urgency"] != "Not Set" else "missing",
            "closure_code_source": "missing", "open_time_source": "original", "resolution_hours_source": "derived",
            "severity_source": "missing", "impact_scope_source": fp.provenance["impact_scope"],
            "reopened_source": "missing", "quality_score": q["score"], "quality_tier": q["tier"],
            "quality_flags": q["flags"], "quality_components": q["components"], "dup_group": cand["incident_id"],
            "near_dup_group": cand["incident_id"], "canonical": True,
            "influence_weight": round(q["score"] * 1.0, 4), "resolution_consistency": q["components"].get("resolution_consistency"),
            "gt_scenario": None, "gt_strategy": None,
        }
        return rec

    # ------------------------------------------------------------------ batch
    def pending_candidates(self) -> list[str]:
        with session_scope() as s:
            rows = s.execute(select(Incident.incident_id).where(Incident.origin == "live", Incident.status == "Resolved",
                                                                Incident.in_kb == False)).scalars().all()  # noqa: E712
            done = set(s.execute(select(KnowledgeQuality.incident_id)).scalars().all())
        return [r for r in rows if r not in done]

    def run_batch(self) -> dict:
        out = []
        for iid in self.pending_candidates():
            try:
                out.append(self.process(iid))
            except Exception as exc:  # noqa: BLE001 — one bad record must not stop the batch
                log.exception("KB evolution failed for %s", iid)
                out.append({"incident_id": iid, "status": "error", "error": str(exc)})
        return {"processed": len(out), "results": out, "ran_at": datetime.utcnow().isoformat()}

    # ------------------------------------------------------------------ feedback on historical evidence
    def apply_feedback_penalty(self, incident_ids: list[str], reason: str) -> list[str]:
        """Negative feedback ('wrong resolution', 'outdated', ...) on a recommendation lowers the
        influence of the historical records that supported it. No model is retrained."""
        changed = []
        with session_scope() as s:
            for iid in incident_ids:
                kq = s.get(KnowledgeQuality, iid)
                rec = self.rt.store.get(iid)
                if kq is None or rec is None:
                    continue
                comps = dict(kq.components or {})
                comps["feedback_penalty"] = round(comps.get("feedback_penalty", 0) + FEEDBACK_PENALTY, 3)
                kq.components = comps
                kq.score = round(max(0.0, kq.score - FEEDBACK_PENALTY), 4)
                kq.flags = sorted(set(kq.flags or []) | {f"feedback:{reason}"})
                rec["influence_weight"] = round(max(0.0, float(rec.get("influence_weight", 0.5)) - FEEDBACK_PENALTY), 4)
                rec["quality_score"] = kq.score
                changed.append(iid)
                _event(s, iid, "feedback_penalty", "applied", reason=reason, new_score=kq.score)
        return changed


def load_accepted_additions(store) -> int:
    """Merge records accepted by the evolution loop (auto or approved) into the in-memory store."""
    try:
        with session_scope() as s:
            rows = s.execute(select(Incident, KnowledgeQuality).join(
                KnowledgeQuality, KnowledgeQuality.incident_id == Incident.incident_id).where(
                Incident.origin == "kb_evolution", Incident.in_kb == True,  # noqa: E712
                KnowledgeQuality.review_status.in_(["auto", "approved"]))).all()
            recs = []
            for inc, kq in rows:
                if store.get(inc.incident_id):
                    continue
                recs.append({
                    "incident_id": inc.incident_id, "title": inc.title, "description": inc.description,
                    "resolution_notes": inc.resolution_notes, "source": "kb_evolution", "category": inc.category or "Application",
                    "ci_name": inc.ci_name or "Unknown", "ci_group": "other", "ci_subcategory": "Unknown",
                    "priority": inc.priority or "Not Set", "impact": inc.impact or "Not Set",
                    "urgency": inc.urgency or "Not Set", "status": "Resolved", "severity": "Unknown",
                    "impact_scope": "Unknown", "suggested_team": None, "open_time": inc.open_time,
                    "resolved_time": inc.resolved_time, "resolution_hours": None, "reopened": None,
                    "no_of_reassignments": None, "related_change": None, "kb_number": None, "text_generator": "engineer",
                    "closure_code": "Not Set", "closure_class": "Unknown", "title_source": "original",
                    "description_source": "original", "resolution_notes_source": "original", "category_source": "derived",
                    "reopened_source": "missing", "quality_score": kq.score, "quality_tier": kq.tier,
                    "quality_flags": kq.flags, "quality_components": kq.components, "dup_group": inc.incident_id,
                    "near_dup_group": inc.incident_id, "canonical": True, "influence_weight": kq.score,
                })
        for r in recs:
            store.add_record(r)
        return len(recs)
    except Exception as exc:  # noqa: BLE001 — a fresh database has no tables yet
        log.info("No KB evolution additions loaded (%s)", exc)
        return 0
