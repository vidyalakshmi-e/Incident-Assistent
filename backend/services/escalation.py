"""Structured escalation packet (owned by the Escalation Agent).

Contents: incident summary, symptoms, metadata, checks performed (incl. clarification attempts and
what was learned), the FULL resolution-attempt history (so L2/L3 do not repeat failed work),
retrieved historical incidents, likely root cause (with evidence strength), suggested team /
expertise, tier with reasons, and the recommended next diagnostic action.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime

from backend.database.session import session_scope
from backend.models.entities import EscalationRecord
from backend.rag.guardrails import classify_action
from backend.services.triage import family_outcome_stats, route_team, route_tier


def likely_root_cause(rt, retrieved_ids: list[str]) -> dict:
    """Root cause supported by the retrieved historical incidents' fingerprints (never asserted
    with certainty: share + support + provenance are always shown)."""
    rcs = []
    for iid in retrieved_ids:
        fp = rt.patterns.fingerprint_of(iid)
        if fp and fp.values["root_cause"] != "Unknown":
            rcs.append((fp.values["root_cause"], fp.provenance["root_cause"], iid))
    if not rcs:
        return {"statement": "insufficient evidence", "support": 0}
    c = Counter(r[0] for r in rcs)
    top, n = c.most_common(1)[0]
    provs = Counter(r[1] for r in rcs if r[0] == top)
    share = n / len(retrieved_ids)
    certainty = "likely" if share >= 0.6 else ("possible" if share >= 0.3 else "weakly supported")
    return {"statement": top, "certainty": certainty, "support": n, "of_retrieved": len(retrieved_ids),
            "share": round(share, 3), "supporting_incidents": [r[2] for r in rcs if r[0] == top],
            "evidence_provenance": dict(provs),
            "tag": "inferred" if provs.get("synthetic", 0) >= provs.get("derived", 0) else "derived",
            "alternatives": {k: v for k, v in c.most_common(4)[1:]}}


def build_packet(rt, *, incident_id: str, text: str, reason: str, bundle=None, attempts: list[dict] | None = None,
                 clarifications: list[dict] | None = None, session_id: str | None = None,
                 remaining_alternatives: list[dict] | None = None, fields: dict | None = None,
                 persist: bool = True) -> dict:
    fields = fields or {}
    attempts = attempts or []
    clarifications = clarifications or []
    fp_vals = bundle.fingerprint.values if bundle else {}
    fam = bundle.families[0] if bundle and bundle.families else None
    fam_obj = rt.patterns.families.get(fam["family_id"]) if fam else None
    fam_stats = family_outcome_stats(rt.store, fam_obj)
    classified = rt.outcome_models.classify_text(text) if rt.outcome_models.available else {}
    priority = fields.get("priority") or (classified.get("priority", {}).get("value"))
    tried_destructive = any(classify_action(a.get("notes") or "")["destructive"] for a in attempts) or         any((alt.get("safety") or {}).get("destructive") for alt in (remaining_alternatives or [])[:1])
    exhausted = any(a["engineer_response"] == "FAILED" for a in attempts) and \
        len([a for a in attempts if a["engineer_response"] == "FAILED"]) >= rt.s.troubleshooting_max_rounds
    tier = route_tier(rt.s.tiers, priority=priority, novel=(bundle.novelty.get("is_novel") if bundle else None),
                      destructive=tried_destructive, troubleshooting_exhausted=exhausted,
                      family_mean_reassignments=fam_stats.get("mean_reassignments"),
                      family_reopen_rate=fam_stats.get("reopen_rate"))
    team = route_team(fp_vals, category=classified.get("category", {}).get("value"))
    retrieved = bundle.retrieval.results[:5] if bundle else []
    rc = likely_root_cause(rt, [r.incident_id for r in retrieved]) if retrieved else {"statement": "insufficient evidence"}
    failed_keys = {a["strategy_key"] for a in attempts if a["engineer_response"] == "FAILED"}
    next_action = None
    for alt in remaining_alternatives or []:
        if alt["strategy_key"] not in failed_keys:
            next_action = {"action": alt["action"], "kind": "untried historical approach",
                           "confidence": alt.get("confidence"), "strategy_key": alt["strategy_key"]}
            break
    if next_action is None:
        comp = fp_vals.get("component", "the affected component")
        next_action = {"action": f"Specialist diagnosis of {comp}: collect logs, metrics and a timeline around the "
                                 f"first occurrence; no untried evidence-backed historical approach remains.",
                       "kind": "system guidance (not from historical evidence)"}
    clar_notes = [{"question": c["question"], "trigger": c["trigger"], "answer": c.get("answer"),
                   "learned": c.get("learned", "no answer yet")} for c in clarifications]
    packet = {
        "packet_id": f"ESC-{uuid.uuid4().hex[:8]}", "created_at": datetime.utcnow().isoformat(),
        "incident_id": incident_id, "session_id": session_id, "reason": reason,
        "tier": tier["tier"], "tier_reasons": tier["reasons"], "tier_order": tier["tier_order"],
        "suggested_team": team["team"], "suggested_expertise": team["expertise"], "routing_basis": team["basis"],
        "incident_summary": text,
        "symptoms": bundle.fingerprint.symptoms if bundle else [],
        "fingerprint": bundle.fingerprint.as_dict() if bundle else None,
        "metadata": {"priority": priority, "priority_source": "reported" if fields.get("priority") else
                     ("predicted from text" if priority else "unknown"),
                     "predicted_classification": classified,
                     "predicted_resolution_time": rt.outcome_models.predict_resolution_hours(
                         {"priority": priority or "Not Set", "ticket_type": "incident"}) if rt.outcome_models.available else None},
        "checks_performed": [
            "hybrid retrieval over the historical knowledge base" + (f" ({', '.join(bundle.retrieval.mode.labels)})" if bundle and bundle.retrieval.mode.labels else ""),
            f"pattern matching → {fam['family_id']} {fam['name']} (match strength {fam['match_strength']})" if fam else "pattern matching → no family",
            f"novelty check → {bundle.novelty.get('verdict')}" if bundle else "novelty check not run",
        ] + [f"clarification ({c['trigger']}): '{c['question']}' → {c['learned']}" for c in clar_notes],
        "clarification": {"attempted": bool(clar_notes), "notes": clar_notes},
        "resolution_attempt_history": attempts,
        "failed_approaches_do_not_repeat": sorted(failed_keys),
        "retrieved_historical_incidents": [
            {"incident_id": r.incident_id, "title": r.title, "relevance_confidence": r.scores.relevance_confidence,
             "family": rt.patterns.assign.get(r.incident_id), "text_provenance": r.provenance.get("description")}
            for r in retrieved],
        "likely_root_cause": rc,
        "family_outcome_history": fam_stats,
        "recommended_next_diagnostic_action": next_action,
        "mode_labels": list(bundle.retrieval.mode.labels) if bundle else [],
    }
    if persist:
        with session_scope() as s:
            s.add(EscalationRecord(incident_id=incident_id, session_id=session_id, tier=packet["tier"],
                                   team=packet["suggested_team"], expertise=packet["suggested_expertise"],
                                   reason=reason, packet=packet))
    return packet
