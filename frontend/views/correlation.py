"""Screen 4 — Live Incident Correlation with 'Simulate Incoming Incident'."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from frontend.api_client import get, post, safe
from frontend.ui import md

PRESETS = {
    "db-outage-burst": "3 differently-worded tickets about slow / timing-out database queries",
    "vpn-storm": "3 tickets about VPN tunnels dropping",
    "memory-leak": "3 tickets about an application getting slower and freezing",
    "unrelated-noise": "3 unrelated tickets (printer, account lockout, SAP dump) — should NOT correlate",
}


def render() -> None:
    st.title("Live Incident Correlation")
    st.caption("New tickets arriving within a short window that share an incident family (from retrieval evidence) or "
               "are textually near-identical are flagged as a possible single ongoing incident.")
    c1, c2 = st.columns([2, 1])
    preset = c1.selectbox("Simulation preset", list(PRESETS), format_func=lambda p: f"{p} — {PRESETS[p]}")
    reset = c2.checkbox("Reset window first", value=True)
    if st.button("▶ Simulate incoming incidents", type="primary"):
        res = safe(post, "/incidents/simulate", {"preset": preset, "reset": reset})
        if res:
            st.session_state["corr_last"] = res
    with st.expander("Inject custom tickets"):
        txt = st.text_area("One ticket per line", "")
        gap = st.number_input("Minutes between tickets", 0.5, 30.0, 3.0)
        if st.button("Inject"):
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            if lines:
                res = safe(post, "/incidents/simulate", {"texts": lines, "interval_minutes": gap, "reset": False})
                if res:
                    st.session_state["corr_last"] = res
    snap = safe(get, "/incidents/correlations")
    if not snap:
        return
    st.caption(f"Window {snap['window_minutes']:.0f} min · alert when ≥ {snap['min_incidents']} related tickets · "
               f"text-similarity threshold {snap['similarity_threshold']:.2f} (validated on simulated streams)")
    for a in snap["alerts"]:
        md(f"<div class='card warn'><span class='kicker'>Correlation alert {a['alert_id']}</span>"
           f"<div class='big'>{html.escape(a['message'])}</div>"
           f"<div class='muted'>members: {', '.join(a['members'])} · family {a['family_id']} · "
           f"shared fingerprint {a['shared_fields'] or '—'} · detection latency {a['detection_latency_s'] / 60:.1f} min "
           f"after the first related ticket · {a['framing']}</div></div>")
    if not snap["alerts"]:
        st.info("No correlation alerts in the current window.")
    if snap["events"]:
        st.markdown("#### Incoming stream")
        df = pd.DataFrame(snap["events"])
        st.dataframe(df[["received_at", "incident_id", "text", "family_id", "alert_id"]], hide_index=True,
                     width="stretch")
    last = st.session_state.get("corr_last")
    if last:
        with st.expander("Last simulation — per-ticket result"):
            for r in last["ingested"]:
                e = r["event"]
                st.write(f"`{e['received_at'][11:16]}` {e['text']} → family **{e['family_id']}** "
                         f"({e['family_basis']}, {e['family_match']}) · correlated with {r['correlated_with'] or '—'}")
