"""Screen 2 — Interactive Troubleshooting ("Have you tried this?") with formal attempt history."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from frontend.api_client import post, safe
from frontend.ui import chip, conf_text, md, mode_banner

DEMO = ("The application is becoming slower and sometimes freezes when users try to open records. "
        "Restarting fixes it temporarily.")


def _call(payload: dict) -> None:
    res = safe(post, "/incidents/troubleshoot", payload)
    if res:
        st.session_state["ts"] = res["session"]
        st.session_state.setdefault("ts_messages", []).extend(res.get("agent_messages", []))


def render_packet(p: dict) -> None:
    md(f"<div class='card warn'><span class='kicker'>Escalation packet {p['packet_id']}</span>"
       f"<div class='big'>{p['tier']} → {html.escape(p['suggested_team'])}"
       f"{' · ' + html.escape(p['suggested_expertise']) if p.get('suggested_expertise') else ''}</div>"
       f"<div class='muted'>Reason: {html.escape(p['reason'])}</div>"
       f"<div class='muted'>Tier reasons: {html.escape('; '.join(p['tier_reasons']))} (tier order: {' → '.join(p['tier_order'])})</div></div>")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Likely root cause**")
        rc = p["likely_root_cause"]
        st.write(rc.get("statement"), f"— {rc.get('certainty', '')} ({rc.get('support', 0)}/{rc.get('of_retrieved', '?')} incidents)")
        st.markdown("**Recommended next diagnostic action**")
        na = p["recommended_next_diagnostic_action"]
        md(f"{html.escape(na['action'])} {chip('derived' if 'historical' in na['kind'] else 'missing', na['kind'])}")
        st.markdown("**Clarification**")
        if p["clarification"]["attempted"]:
            for c in p["clarification"]["notes"]:
                st.write(f"Asked ({c['trigger']}): *{c['question']}* → learned: **{c['learned']}**")
        else:
            st.write("No clarification was attempted.")
    with c2:
        st.markdown("**Checks performed**")
        for c in p["checks_performed"]:
            st.write("• " + c)
        st.markdown("**Do not repeat (failed approaches)**")
        st.write(", ".join(p["failed_approaches_do_not_repeat"]) or "—")
    if p["resolution_attempt_history"]:
        st.markdown("**Full resolution-attempt history**")
        st.dataframe(pd.DataFrame(p["resolution_attempt_history"])[
            ["round", "step_description", "engineer_response", "timestamp", "excluded_from_next_suggestion", "strategy_key"]],
            hide_index=True, width="stretch")
    with st.expander("Raw packet JSON"):
        st.json(p)


def render() -> None:
    st.title("Guided Troubleshooting")
    st.caption("One actionable step at a time. Every attempt is recorded; failed approaches are excluded from the next "
               "suggestion. A clarifying question may be asked (at most once) before escalating.")
    prefill = st.session_state.pop("ts_prefill", None)
    ts = st.session_state.get("ts")
    if ts is None or prefill:
        text = st.text_area("Incident description", value=(prefill[1] if prefill else DEMO), height=90)
        if st.button("Start troubleshooting", type="primary"):
            st.session_state["ts_messages"] = []
            _call({"action": "start", "text": text, "incident_id": prefill[0] if prefill else None})
            st.rerun()
        return
    top = st.columns([4, 1])
    top[0].markdown(f"**Session** `{ts['session_id']}` · incident `{ts['incident_id']}` · status **{ts['status']}** · "
                    f"round {ts['round']}/{ts['max_rounds']}")
    if top[1].button("New session"):
        st.session_state.pop("ts", None)
        st.rerun()
    mode_banner(ts.get("mode_labels"))
    st.caption(ts["query"])
    if ts.get("family"):
        st.caption(f"Pattern: {ts['family']['family_id']} {ts['family']['name']} (match {ts['family']['match_strength']})")

    if ts["status"] == "active" and ts.get("current_step"):
        cs = ts["current_step"]
        notes = "".join(f"<div class='muted'>⚠ {html.escape(n)}</div>" for n in cs["safety"]["notes"])
        md(f"<div class='card primary'><span class='kicker'>Step {cs['round']} · have you tried this?</span>"
           f"<div class='big'>☐ {html.escape(cs['action'])}</div><div class='step'>{html.escape(cs['step'])}</div>"
           f"<div class='muted'>Expected observation: {html.escape(cs.get('expected_observation') or '—')}</div>"
           f"<div>Confidence: {conf_text(cs['confidence'], cs['confidence_basis'])}</div>"
           f"<div class='muted'>Evidence: {', '.join(cs['supporting_incidents'][:6])}</div>{notes}</div>")
        eng_notes = st.text_input("Notes for this attempt (optional)")
        c1, c2, c3, c4 = st.columns(4)
        for col, resp, kind in ((c1, "WORKED", "primary"), (c2, "FAILED", "secondary"), (c3, "UNKNOWN", "secondary")):
            if col.button(resp, type=kind, width="stretch"):
                _call({"action": "respond", "session_id": ts["session_id"], "attempt_id": cs["attempt_id"],
                       "response": resp, "notes": eng_notes or None})
                st.rerun()
        if c4.button("Escalate now", width="stretch"):
            _call({"action": "escalate", "session_id": ts["session_id"], "reason": "requested by engineer"})
            st.rerun()
    elif ts["status"] == "awaiting_clarification":
        q = ts["clarification"]
        md(f"<div class='card warn'><span class='kicker'>One quick question ({q['trigger'].replace('_', ' ')})</span>"
           f"<div class='big'>{html.escape(q['question'])}</div><div class='muted'>Why: {html.escape(q['reason'])}</div></div>")
        choice = st.radio("Answer", q["options"] + ["(type my own answer)"], index=0)
        free = st.text_input("Your answer") if choice == "(type my own answer)" else None
        c1, c2 = st.columns(2)
        if c1.button("Answer", type="primary"):
            _call({"action": "clarify", "session_id": ts["session_id"], "answer": free or choice})
            st.rerun()
        if c2.button("Skip — I don't know"):
            _call({"action": "clarify", "session_id": ts["session_id"], "declined": True})
            st.rerun()
    elif ts["status"] == "resolved":
        st.success(f"Resolved by: {ts['resolved_by']['step_description']}")
        st.info("Next: rate the recommendation (Feedback page) and/or generate a postmortem — both feed the Knowledge "
                "Base Evolution loop so this incident becomes retrievable knowledge.")
        c1, c2 = st.columns(2)
        if c1.button("Generate postmortem + update KB", type="primary"):
            res = safe(post, "/postmortem", {"incident_id": ts["incident_id"], "feed_to_kb": True})
            if res:
                st.session_state["last_postmortem"] = res
        if c2.button("Go to feedback"):
            st.session_state["feedback_prefill"] = {"incident_id": ts["incident_id"], "session_id": ts["session_id"]}
            st.switch_page(st.session_state["pages"]["feedback"])
        pm = st.session_state.get("last_postmortem")
        if pm and pm["postmortem"]["incident_id"] == ts["incident_id"]:
            p = pm["postmortem"]
            st.subheader("Postmortem")
            st.write("**What happened:**", p["what_happened"])
            st.write("**Impact:**", p["impact"]["business_impact"], "·", p["impact"]["impact_scope"])
            st.write("**Root cause:**", p["root_cause"].get("statement", "insufficient evidence"), f"({p['root_cause']['tag']})")
            st.write("**Final fix:**", (p["final_fix"] or {}).get("step_description"))
            st.markdown("**Preventive recommendations**")
            for r in p["preventive_recommendations"]:
                st.write(f"• {r['recommendation']}  _({r['framing']})_")
            st.markdown("**Timeline**")
            st.dataframe(pd.DataFrame(p["timeline"]), hide_index=True, width="stretch")
            if pm.get("kb_update"):
                ku = pm["kb_update"]
                (st.success if ku["status"] == "added_to_kb" else st.warning)(
                    f"KB evolution: {ku['status']} (quality {ku['quality']['score']}) "
                    + (f"→ family {ku.get('family_id')}" if ku.get("family_id") else ku.get("note", "")))
    elif ts["status"] == "novel":
        md(f"<div class='card novel'><div class='big'>{html.escape(ts['novelty']['verdict'])}</div>"
           f"<div class='muted'>No historical playbook — route to fresh investigation.</div></div>")
        if st.button("Escalate for fresh investigation", type="primary"):
            _call({"action": "escalate", "session_id": ts["session_id"], "reason": "novel incident"})
            st.rerun()
    if ts.get("escalation"):
        render_packet(ts["escalation"])

    if ts["attempts"]:
        st.markdown("#### Attempt log (formal tracking)")
        df = pd.DataFrame(ts["attempts"])[["attempt_id", "round", "step_description", "expected_observation",
                                           "engineer_response", "timestamp", "excluded_from_next_suggestion"]]
        st.dataframe(df, hide_index=True, width="stretch")
    if ts["clarifications"]:
        st.markdown("#### Clarifications")
        for c in ts["clarifications"]:
            st.write(f"• ({c['trigger']}) *{c['question']}* → {c.get('learned', 'pending')}")
    with st.expander("Session timeline and agent messages"):
        for e in ts["events"]:
            st.write(f"`{e['at'][11:19]}` {e['kind']} — { {k: v for k, v in e.items() if k not in ('at', 'kind')} }")
        for m in st.session_state.get("ts_messages", []):
            st.write(f"`{m['sender']}` → `{m['recipient']}` · **{m['intent']}** — {m['summary']}")
