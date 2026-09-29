"""Screen 8 — Knowledge Quality & Knowledge Base Evolution."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.api_client import get, post, safe
from frontend.ui import LEGEND, chip, md


def render() -> None:
    st.title("Knowledge Quality & KB Evolution")
    q = safe(get, "/kb/quality")
    if q:
        c = st.columns(4)
        c[0].metric("KB records", q["records"])
        c[1].metric("High quality", q["tiers"].get("high", 0))
        c[2].metric("Medium", q["tiers"].get("medium", 0))
        c[3].metric("Low", q["tiers"].get("low", 0))
        md(f"Text provenance of the KB: {q['text_provenance']} &nbsp; {LEGEND}")
        h = pd.Series(q["score_histogram"])
        fig = go.Figure(go.Bar(x=h.index.astype(str), y=h.values, marker_color="#2d5fa8"))
        fig.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="quality score (rounded)")
        st.plotly_chart(fig, width="stretch")
        st.markdown("**Quality flags**")
        st.dataframe(pd.Series(q["flag_counts"], name="records").sort_values(ascending=False), width="stretch")
        with st.expander("Lowest-quality records (reduced influence during resolution synthesis)"):
            st.dataframe(pd.DataFrame(q["lowest_quality"]), hide_index=True, width="stretch")
    st.divider()
    st.subheader("Knowledge Base Evolution loop")
    st.caption("Resolved incident → attempt history + outcome → engineer feedback → quality re-score → "
               "(≥ threshold) fingerprint → family → graph → vector + BM25 index · (< threshold) manual review. "
               "Runs on demand per resolved incident and as a nightly batch (scripts/kb_evolution_batch.py).")
    ev = safe(get, "/kb/evolution")
    if st.button("Run KB evolution batch now"):
        res = safe(post, "/kb/evolve", {})
        if res:
            st.success(f"Processed {res['processed']} pending resolved incident(s).")
            ev = safe(get, "/kb/evolution")
    if not ev:
        return
    st.markdown("**Recently added knowledge**")
    if not ev["recently_added"]:
        st.info("Nothing added yet — resolve an incident on the Troubleshooting page and submit feedback / a postmortem.")
    for r in ev["recently_added"]:
        prov = r.get("provenance") or {}
        md(f"<div class='card primary'><b>{r['incident_id']}</b> → family {r['family_id']} · quality {r['quality']} "
           f"({r['tier']}) · added {str(r['added_at'])[:19]}<div class='muted'>{html.escape(r['title'] or '')}</div>"
           f"<div>{html.escape(r['resolution_notes'] or '')}</div>"
           f"<div>description {chip(prov.get('description'))} resolution {chip(prov.get('resolution_notes'))} "
           f"category {chip(prov.get('category'))}</div></div>")
    st.markdown("**Pending manual review**")
    if not ev["pending_review"]:
        st.caption("No records waiting for review.")
    for r in ev["pending_review"]:
        md(f"<div class='card warn'><b>{r['incident_id']}</b> quality {r['quality']} flags {r['flags']}"
           f"<div>{html.escape(r['resolution_notes'] or '')}</div></div>")
        c1, c2 = st.columns(2)
        if c1.button("Approve", key=f"ap_{r['incident_id']}"):
            safe(post, f"/kb/review/{r['incident_id']}", {"approve": True})
            st.rerun()
        if c2.button("Reject", key=f"rj_{r['incident_id']}"):
            safe(post, f"/kb/review/{r['incident_id']}", {"approve": False})
            st.rerun()
    if ev["pending_candidates"]:
        st.caption(f"Resolved but not yet processed: {', '.join(ev['pending_candidates'])}")
    with st.expander("Audit trail (kb_evolution_events)"):
        if ev["events"]:
            st.dataframe(pd.DataFrame(ev["events"]), hide_index=True, width="stretch")
