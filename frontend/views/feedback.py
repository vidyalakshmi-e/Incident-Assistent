"""Screen 7 — Feedback submission (feeds Knowledge Base Evolution)."""
from __future__ import annotations

import streamlit as st

from frontend.api_client import post, safe

REASONS = ["wrong incident", "wrong resolution", "incomplete", "outdated", "escalation required", "other"]


def _tri(label: str, key: str):
    v = st.radio(label, ["not answered", "yes", "no"], horizontal=True, key=key)
    return None if v == "not answered" else v == "yes"


def render() -> None:
    st.title("Feedback")
    st.caption("Feedback changes knowledge records (quality, influence of the evidence that was used) and triggers the "
               "KB evolution loop for resolved incidents. It does not retrain any model.")
    pre = st.session_state.get("feedback_prefill", {})
    last = st.session_state.get("analysis") or {}
    incident_id = st.text_input("Incident ID", value=pre.get("incident_id") or last.get("incident_id", ""))
    session_id = st.text_input("Troubleshooting session ID (optional)", value=pre.get("session_id", ""))
    c1, c2 = st.columns(2)
    thumbs = c1.radio("Was the recommendation helpful?", ["👍 yes", "👎 no", "skip"], horizontal=True)
    reasons = c2.multiselect("Reasons (optional)", REASONS)
    q1 = _tri("Was the root cause correct?", "rc")
    q2 = _tri("Was the pattern / family correct?", "pc")
    q3 = _tri("Did troubleshooting resolve it?", "tr")
    q4 = _tri("Was escalation appropriate?", "ea")
    comment = st.text_area("Comment (optional)")
    supporting = (last.get("top_resolution") or {}).get("supporting_incidents", [])
    if supporting:
        st.caption(f"The rated recommendation was backed by: {', '.join(supporting)} (negative feedback lowers their "
                   f"influence in future rankings)")
    if st.button("Submit feedback", type="primary") and incident_id:
        payload = {"incident_id": incident_id, "session_id": session_id or None,
                   "helpful": None if thumbs == "skip" else thumbs.startswith("👍"), "reasons": reasons,
                   "root_cause_correct": q1, "pattern_correct": q2, "troubleshooting_resolved": q3,
                   "escalation_appropriate": q4, "comment": comment or None,
                   "supporting_incident_ids": supporting or None}
        res = safe(post, "/incidents/feedback", payload)
        if res:
            st.success("Feedback recorded.")
            if res["penalised_records"]:
                st.info(f"Lowered influence of: {', '.join(res['penalised_records'])}")
            if res["kb_update"]:
                k = res["kb_update"]
                (st.success if k["status"] == "added_to_kb" else st.warning)(
                    f"Knowledge base update: {k['status']} (quality {k['quality']['score']}). "
                    + (f"Assigned to family {k['family_id']}{' (new emerging family)' if k.get('family_created') else ''}; "
                       f"now retrievable." if k["status"] == "added_to_kb" else k.get("note", "")))
