"""Screen 3 — Incident Pattern Explorer (families, symptoms, root causes, recurrence, causal chain, graph)."""
from __future__ import annotations

import html
import math

import networkx as nx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.api_client import get, safe
from frontend.ui import causal_chain_dot, chip, md


def family_graph_figure(graph: dict, highlight: str | None) -> go.Figure:
    g = nx.Graph()
    for n in graph["nodes"]:
        g.add_node(n["id"], **n)
    for l in graph["links"]:
        g.add_edge(l["source"], l["target"], **{k: v for k, v in l.items() if k not in ("source", "target")})
    pos = nx.spring_layout(g, seed=7, k=0.9 / math.sqrt(max(1, g.number_of_nodes())))
    colors = {"family": "#2d5fa8", "root_cause": "#a36a00", "component": "#1f7a4d"}
    traces = []
    for style, dash in (("derived", "dash"), ("observed", "solid")):
        xs, ys = [], []
        for a, b, d in g.edges(data=True):
            if d.get("tag") == style:
                xs += [pos[a][0], pos[b][0], None]
                ys += [pos[a][1], pos[b][1], None]
        traces.append(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=1, color="#9aa4b2", dash=dash),
                                 hoverinfo="none", name=f"{style} link"))
    for kind, color in colors.items():
        nodes = [n for n, d in g.nodes(data=True) if d.get("kind") == kind]
        traces.append(go.Scatter(
            x=[pos[n][0] for n in nodes], y=[pos[n][1] for n in nodes], mode="markers+text" if kind == "family" else "markers",
            text=[n if kind == "family" else "" for n in nodes], textposition="top center",
            hovertext=[f"{g.nodes[n].get('label')} (size {g.nodes[n].get('size', '')})" for n in nodes],
            hoverinfo="text", name=kind.replace("_", " "),
            marker=dict(size=[8 + 2.2 * math.sqrt(g.nodes[n].get("size", 4)) if kind == "family" else 9 for n in nodes],
                        color=color, line=dict(width=[3 if n == highlight else 0 for n in nodes], color="#b42318"))))
    fig = go.Figure(traces)
    fig.update_layout(height=520, margin=dict(l=0, r=0, t=10, b=0), showlegend=True,
                      xaxis=dict(visible=False), yaxis=dict(visible=False), legend=dict(orientation="h"))
    return fig


def render() -> None:
    st.title("Incident Pattern Explorer")
    st.caption("Families discovered by clustering the enriched fingerprint (semantic + resolution + fingerprint fields). "
               "Family membership of Source B rows is derived from generated text; timestamps and outcomes are original.")
    data = safe(get, "/patterns")
    if not data:
        return
    fams = pd.DataFrame(data["families"])
    fams["root cause"] = fams["signature"].map(lambda s: next((k for k in s.get("root_cause", {}) if k != "Unknown"), "Unknown"))
    fams["text provenance"] = fams.apply(lambda r: f"{r['members_original_text']} original / {r['members_synthetic_text']} synthetic", axis=1)
    c1, c2, c3 = st.columns(3)
    c1.metric("Families", len(fams))
    c2.metric("Cross-symptom findings", len(data["cross_symptom_findings"]))
    c3.metric("Clusters chosen by silhouette (k)", data["meta"].get("k_selected"))
    st.dataframe(fams[["family_id", "name", "size", "status", "root cause", "text provenance", "n_strategies"]],
                 hide_index=True, width="stretch", height=280)
    fid = st.selectbox("Explore family", fams["family_id"].tolist(),
                       format_func=lambda f: f"{f} — {fams.set_index('family_id').at[f, 'name']}")
    fam = safe(get, f"/patterns/{fid}")
    if not fam:
        return
    t1, t2, t3, t4, t5 = st.tabs(["Signature", "Causal chain", "Recurrence", "Strategies", "Graph"])
    with t1:
        cols = st.columns(3)
        for i, fld in enumerate(["component", "symptom", "root_cause", "failure_type", "trigger", "impact_scope"]):
            with cols[i % 3]:
                st.markdown(f"**{fld.replace('_', ' ')}**")
                for v, share in fam["signature"].get(fld, {}).items():
                    st.progress(min(1.0, share), text=f"{v} — {share:.0%}")
        if fam.get("cross_symptom"):
            cs = fam["cross_symptom"]
            st.success(f"Cross-symptom root-cause discovery: {cs['finding']} — {cs['symptoms']}")
        st.markdown("**Sample members**")
        for m in fam["members_sample"][:8]:
            md(f"<div class='muted'><b>{m['incident_id']}</b> {chip(m['description_source'], 'text ' + m['description_source'])} "
               f"{html.escape(m['description'] or '')}</div>")
    with t2:
        st.caption("Aggregated over members that have timestamps. Border style = dominant tag: solid observed · dashed "
                   "derived · dotted inferred. Stages without data say 'insufficient evidence'.")
        st.graphviz_chart(causal_chain_dot(fam["causal_chain"]))
        st.dataframe(pd.DataFrame(fam["causal_chain"]), hide_index=True, width="stretch")
        st.markdown("**Example incident chains**")
        for ch in fam["example_causal_chains"]:
            if not ch:
                continue
            if ch["available"]:
                st.graphviz_chart(causal_chain_dot(ch["links"]))
            else:
                st.info(f"{ch['incident_id']}: {ch['reason']}")
    with t3:
        rec = fam["recurrence"] or {}
        if rec.get("status") != "ok":
            st.info(f"Recurrence: {rec.get('status', 'no data')}")
        else:
            mc = pd.Series(rec["monthly_counts"])
            fig = go.Figure(go.Bar(x=mc.index, y=mc.values, marker_color="#2d5fa8"))
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="incidents / month")
            st.plotly_chart(fig, width="stretch")
            st.caption(rec["provenance_note"])
            if rec.get("finding"):
                st.warning(rec["finding"])
            st.dataframe(pd.DataFrame(rec["recurring_cis"]), hide_index=True, width="stretch")
    with t4:
        for s in fam["strategies"]:
            stats = (f"reopen {s['reopen_rate']:.1%} (95% CI {s['reopen_ci_low']:.1%}–{s['reopen_ci_high']:.1%}) · "
                     f"median {s['median_resolution_hours']} h" if s.get("stats_supported")
                     else "historical resolutions observed — no success statistics")
            md(f"<div class='card'><b>{s['strategy_key']}</b> · {html.escape(s['label'])} "
               f"<span class='muted'>({s['n_incidents']} incidents, wording {s['text_provenance']})</span>"
               f"<div class='muted'>{stats}</div></div>")
    with t5:
        graph = safe(get, "/patterns/graph")
        if graph:
            st.plotly_chart(family_graph_figure(graph, fid), width="stretch")
            st.caption("Blue = families (size ∝ members), amber = root causes, green = components. Dashed links are "
                       "derived (shared dominant root cause / fingerprint), solid links are observed (shared CIs).")
    st.subheader("Proactive prevention — potential patterns requiring investigation")
    st.caption("Computed on ALL 46,606 real structured incidents (original fields only). These are prompts to "
               "investigate, not predictions.")
    st.dataframe(pd.DataFrame(data["proactive"]["ci_hotspots"])[
        ["ci_name", "ci_subcategory", "total_incidents", "max_in_14_days", "top_closure_codes", "reopen_rate", "finding"]],
        hide_index=True, width="stretch")
    ft = data["proactive"]["family_transitions"]
    st.caption(f"Failure-chain candidates (family A → B on the same CI within {ft['window_days']} days, support ≥ 5, "
               f"lift ≥ 2): {len(ft['chains'])} found. {ft.get('note', '')} Tag: {ft['tag']}")
    if ft["chains"]:
        st.dataframe(pd.DataFrame(ft["chains"]), hide_index=True)
