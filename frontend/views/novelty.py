"""Screen 5 — Novel Incident Detection."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.api_client import get, post, safe
from frontend.ui import md

EXAMPLES = [
    "The GPS time server in the data center lost satellite lock and trading hosts drift from UTC.",
    "Users cannot log in to the HR portal, they are sent back to the login page after entering credentials.",
    "Robotic tape library arm is jammed and the offsite tape rotation cannot be performed.",
]


def render() -> None:
    st.title("Novel Incident Detection")
    st.caption("Decides whether an incident resembles known patterns strongly enough. If not, the system says "
               "NOVEL INCIDENT and routes to fresh investigation instead of forcing a low-confidence match.")
    text = st.selectbox("Try an example", EXAMPLES + ["(type my own)"])
    if text == "(type my own)":
        text = st.text_area("Incident description")
    if st.button("Check novelty", type="primary") and text:
        res = safe(post, "/incidents/search", {"query": text, "top_k": 5})
        if res:
            st.session_state["nov"] = res
    res = st.session_state.get("nov")
    if res:
        n = res["novelty"]
        if n.get("is_novel") is None:
            st.warning(f"Undetermined: {n['basis']}")
        else:
            cls = "novel" if n["is_novel"] else "primary"
            md(f"<div class='card {cls}'><div class='big'>{html.escape(n['verdict'])}</div>"
               f"<div class='muted'>P(known) = {n['known_probability']:.3f} vs. validated threshold {n['threshold']:.3f} → "
               f"{html.escape(n['recommended_route'])}</div></div>")
            fig = go.Figure(go.Indicator(mode="gauge+number", value=n["known_probability"],
                                         gauge={"axis": {"range": [0, 1]}, "bar": {"color": "#2d5fa8"},
                                                "threshold": {"line": {"color": "#b42318", "width": 3},
                                                              "value": n["threshold"]}},
                                         title={"text": "P(known pattern)"}))
            fig.update_layout(height=230, margin=dict(l=20, r=20, t=40, b=0))
            st.plotly_chart(fig, width="stretch")
            c = pd.DataFrame({"feature": list(n["features"]), "value": list(n["features"].values()),
                              "contribution to log-odds": [n["contributions"][f] for f in n["features"]]})
            st.dataframe(c, hide_index=True, width="stretch")
        st.caption("Nearest historical incidents (shown for transparency; NOT used as a recommendation when novel):")
        for r in res["results"][:3]:
            st.write(f"• {r['incident_id']} — {r['title']} (relevance {r['scores']['relevance_confidence']})")
    ev = safe(get, "/evaluation")
    if ev and ev.get("novelty"):
        nv = ev["novelty"]
        st.subheader("How the threshold was chosen")
        st.write(f"Rule: **{nv['validation'].get('selection_rule', '')}** on the validation split; reported on the "
                 f"held-out test split (threshold P(known) = {nv['threshold_p_known']:.3f}).")
        t = nv["test"]
        cols = st.columns(4)
        cols[0].metric("Precision (novel)", f"{t['precision']:.3f}")
        cols[1].metric("Recall (novel)", f"{t['recall']:.3f}")
        cols[2].metric("False-novel rate", f"{t['false_novel_rate']:.3f}")
        cols[3].metric("False-known rate", f"{t['false_known_rate']:.3f}")
        st.caption(f"Test set: {t['n_known']} known paraphrased incidents, {t['n_novel']} seeded no-match probes.")
