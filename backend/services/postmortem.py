"""One-click structured postmortem for a resolved incident; feeds the KB Evolution loop.

Sections: what happened, impact, timeline, root cause (with evidence tag), resolution attempt
history, final fix, preventive recommendations (framed as "potential pattern requiring
investigation"). Every section is assembled from recorded data; an optional LLM narrative is
added separately and labelled as LLM-generated.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from backend.database.session import session_scope
from backend.evidence.chain import root_cause_evidence
from backend.models.entities import IncidentFeedback, Postmortem, TroubleshootingSession
from backend.services.analysis import analyze_text
from backend.services.incidents import incident_row
from backend.troubleshooting.attempts import AttemptTracker

WORKAROUND_WORDS = ("restart", "recycl", "reboot", "power-cycl", "clear", "logged it off", "workaround")


def generate(rt, incident_id: str, sidx=None) -> dict:
    inc = incident_row(incident_id)
    if inc is None:
        raise KeyError(incident_id)
    attempts = AttemptTracker().for_incident(incident_id)
    with session_scope() as s:
        sess = s.execute(select(TroubleshootingSession).where(TroubleshootingSession.incident_id == incident_id)
                         .order_by(TroubleshootingSession.created_at.desc())).scalars().first()
        state = dict(sess.state) if sess else {}
        fb = s.execute(select(IncidentFeedback).where(IncidentFeedback.incident_id == incident_id)
                       .order_by(IncidentFeedback.created_at.desc())).scalars().first()
        fb_d = None if fb is None else {"root_cause_correct": fb.root_cause_correct, "helpful": fb.helpful}
    text = inc["description"] or inc["title"] or ""
    bundle = analyze_text(rt, text, hints=state.get("hints", {}))
    rc = root_cause_evidence(rt, [r.incident_id for r in bundle.retrieval.results[:5]])
    if fb_d and fb_d.get("root_cause_correct") is True and rc.get("status") == "computed":
        rc["confirmed_by_engineer"] = True
    worked = [a for a in attempts if a["engineer_response"] == "WORKED"]
    failed = [a for a in attempts if a["engineer_response"] == "FAILED"]
    fam = bundle.families[0] if bundle.families else None
    fam_obj = rt.patterns.families.get(fam["family_id"]) if fam else None

    timeline = [{"at": inc["open_time"], "event": "incident opened"}]
    for e in state.get("events", []):
        timeline.append({"at": e["at"], "event": e["kind"].replace("_", " "),
                         "detail": {k: v for k, v in e.items() if k not in ("at", "kind")}})
    if inc.get("resolved_time"):
        timeline.append({"at": inc["resolved_time"], "event": "incident resolved"})

    prevent = []
    if worked and any(w in worked[-1]["step_description"].lower() for w in WORKAROUND_WORDS) and sidx and fam:
        permanent = [st for st in sidx.by_family.get(fam["family_id"], [])
                     if st["strategy_key"] != worked[-1]["strategy_key"]
                     and not any(w in st["label"].lower() for w in WORKAROUND_WORDS)]
        if permanent:
            p = permanent[0]
            prevent.append({"recommendation": f"The fix applied looks like a workaround. Historically this pattern was "
                                              f"also resolved by: {p['label']}",
                            "basis": f"strategy {p['strategy_key']} observed in {p['n_incidents']} incidents",
                            "framing": "potential pattern requiring investigation"})
    if fam_obj and fam_obj.extra.get("recurrence", {}).get("finding"):
        prevent.append({"recommendation": fam_obj.extra["recurrence"]["finding"],
                        "basis": "recurrence analysis over real timestamps",
                        "framing": "potential pattern requiring investigation"})
    if failed:
        prevent.append({"recommendation": "Update the runbook: the following approaches did not work for this "
                                          "incident — " + "; ".join(a["step_description"] for a in failed),
                        "basis": "formal attempt records", "framing": "knowledge update"})
    content = {
        "incident_id": incident_id, "generated_at": datetime.utcnow().isoformat(),
        "what_happened": text,
        "impact": {"business_impact": bundle.fingerprint.values["business_impact"],
                   "impact_scope": bundle.fingerprint.values["impact_scope"],
                   "provenance": {k: bundle.fingerprint.provenance[k] for k in ("business_impact", "impact_scope")}},
        "timeline": timeline,
        "root_cause": {**rc, "tag": "inferred from matched historical incidents"
                       + (" — confirmed by engineer feedback" if rc.get("confirmed_by_engineer") else "")},
        "pattern": {"family_id": fam["family_id"], "name": fam["name"], "match_strength": fam["match_strength"]} if fam else None,
        "resolution_attempt_history": attempts,
        "final_fix": worked[-1] if worked else None,
        "preventive_recommendations": prevent or [{"recommendation": "No preventive pattern met the evidence bar.",
                                                   "basis": "-", "framing": "-"}],
        "clarifications": state.get("clarifications", []),
        "llm_narrative": None,
    }
    if rt.llm.available:
        narrative = rt.llm.complete(
            "Write a 4-sentence blameless postmortem summary from these facts only:\n"
            f"What happened: {text}\nFinal fix: {worked[-1]['step_description'] if worked else 'none'}\n"
            f"Failed attempts: {', '.join(a['step_description'] for a in failed) or 'none'}\n"
            f"Likely root cause: {rc.get('statement', 'unknown')}", max_tokens=220, purpose="postmortem")
        content["llm_narrative"] = {"text": narrative, "kind": "LLM-generated synthesis"} if narrative else None
    with session_scope() as s:
        pm = Postmortem(incident_id=incident_id, content=content, fed_to_kb=False)
        s.add(pm)
        s.flush()
        content["postmortem_id"] = pm.id
    return content
