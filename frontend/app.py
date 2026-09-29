"""Streamlit frontend — Incident Intelligence Platform.

Run: streamlit run frontend/app.py   (expects the API at $API_URL, default http://localhost:8000)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from frontend import ui  # noqa: E402
from frontend.api_client import API_URL, get  # noqa: E402
from frontend.views import (  # noqa: E402
    assistant, correlation, evaluation, feedback, knowledge, novelty, patterns, troubleshooting,
)

st.set_page_config(page_title="Incident Intelligence", page_icon="🛰️", layout="wide")
ui.setup()

pages = {
    "assistant": st.Page(assistant.render, title="Incident Assistant", icon="🧭", url_path="assistant", default=True),
    "troubleshooting": st.Page(troubleshooting.render, title="Guided Troubleshooting", icon="🛠️", url_path="troubleshooting"),
    "patterns": st.Page(patterns.render, title="Pattern Explorer", icon="🧬", url_path="patterns"),
    "correlation": st.Page(correlation.render, title="Live Correlation", icon="📡", url_path="correlation"),
    "novelty": st.Page(novelty.render, title="Novel Incidents", icon="✨", url_path="novelty"),
    "feedback": st.Page(feedback.render, title="Feedback", icon="👍", url_path="feedback"),
    "knowledge": st.Page(knowledge.render, title="Knowledge Quality & Evolution", icon="📚", url_path="knowledge"),
    "evaluation": st.Page(evaluation.render, title="Evaluation Dashboard", icon="📊", url_path="evaluation"),
}
st.session_state["pages"] = pages
nav = st.navigation({"Operate": [pages[k] for k in ("assistant", "troubleshooting", "correlation", "novelty")],
                     "Understand": [pages[k] for k in ("patterns", "knowledge")],
                     "Improve": [pages[k] for k in ("feedback", "evaluation")]})

with st.sidebar:
    st.markdown("### 🛰️ Incident Intelligence")
    st.caption("Decision support — never an autonomous administrator. Destructive actions always need a human.")
    try:
        h = get("/health")
        llm = h["llm"]
        st.markdown(f"**LLM:** {'✅ ' + llm['model'] if llm['available'] else '⚠ retrieval-only mode'}")
        if not llm["available"]:
            st.caption(llm["reason"])
        st.markdown(f"**Vector DB:** {'✅' if h['vector_store']['ok'] else '⚠ keyword-only'} · "
                    f"**Reranker:** {'✅' if 'none' not in h['reranker']['provider'] else '⚠ unreranked'}")
        st.caption(f"KB {h['knowledge_base']['records']} records · {h['knowledge_base']['families']} families · "
                   f"tiers {' → '.join(h['escalation_tiers'])}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"API not reachable at {API_URL}: {exc}")

nav.run()
