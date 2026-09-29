"""Screen 6 — dedicated Evaluation Dashboard (numbers computed by scripts/run_evaluation.py)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from frontend.api_client import get, safe


def _metrics_row(d: dict, keys: list[tuple[str, str]]) -> None:
    cols = st.columns(len(keys))
    for c, (k, label) in zip(cols, keys):
        v = d.get(k)
        c.metric(label, "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v)))


def render() -> None:
    st.title("Evaluation Dashboard")
    ev = safe(get, "/evaluation")
    if not ev:
        st.info("Run `python scripts/run_evaluation.py` to compute the metrics.")
        return
    st.caption(f"Run {ev['run_id']} · {ev['created_at'][:19]} UTC · dataset {ev['dataset_fingerprint']} · "
               f"query set {ev['query_set']} · generator {ev['query_generator']} · all numbers computed by code "
               f"(scripts/run_evaluation.py), none hand-entered.")
    tabs = st.tabs(["Retrieval", "RAG", "Classification & prediction", "Patterns & causal chains", "Novelty",
                    "Troubleshooting", "Correlation", "Evidence chain & KB quality", "Latency"])
    with tabs[0]:
        r = ev["retrieval"]
        st.caption(r["relevance"])
        df = pd.DataFrame(r["configs"]).T
        st.dataframe(df[["MRR", "P@1", "P@5", "Hit@1", "Hit@5", "nDCG@5", "nDCG@10", "R@10"]].style.format("{:.3f}"),
                     width="stretch")
        fig = go.Figure([go.Bar(name=m, x=df.index, y=df[m]) for m in ("MRR", "P@5", "nDCG@10")])
        fig.update_layout(barmode="group", height=320, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Main configuration: {r['main_config']} · bootstrap 95% CIs: {r['bootstrap_95ci_main']} · "
                   f"{r['recall_note']}")
        st.dataframe(pd.DataFrame(r["by_query_style"]).T, width="stretch")
    with tabs[1]:
        g = ev["rag"]
        st.caption(f"Mode: {g['mode']}")
        _metrics_row(g, [("context_precision@5", "Context precision@5"), ("context_recall", "Context recall"),
                         ("answer_relevancy_embedding", "Answer relevancy (emb.)"),
                         ("family_accuracy@1", "Family accuracy@1"),
                         ("resolution_strategy_accuracy@1", "Strategy accuracy@1")])
        st.write(f"**Faithfulness:** {g['faithfulness']['value']} — {g['faithfulness']['basis']}")
        st.write("**RAGAS non-LLM metrics:**", g["ragas_non_llm"])
        st.write("**RAGAS LLM-judged metrics:**", g["ragas_llm_metrics"]["status"])
        llm = ev.get("rag_llm_mode", {})
        st.markdown("**LLM mode (generated synthesis)**")
        if llm.get("status") == "computed":
            _metrics_row(llm, [("faithfulness_nli", "Faithfulness (NLI)"), ("answer_relevancy_embedding", "Answer relevancy"),
                               ("validator_all_grounded_rate", "Validator: all grounded"), ("n", "Queries")])
            st.caption(f"LLM {llm['llm']} · judge: {llm['judge']}")
        else:
            st.info(llm.get("status"))
        if g.get("confidence_vs_accuracy"):
            st.markdown("**Is the displayed confidence meaningful?** (strategy accuracy by confidence bucket)")
            st.dataframe(pd.DataFrame(g["confidence_vs_accuracy"]).T, width="stretch")
        with st.expander("Definitions"):
            st.json(g["definitions"])
    with tabs[2]:
        st.markdown("**Text classifiers** (used when structured fields are missing)")
        rows = {k: {m: v[m] for m in ("accuracy", "macro_precision", "macro_recall", "macro_f1", "weighted_f1",
                                      "majority_class_baseline_accuracy", "n_test")} for k, v in ev["classification"].items()}
        st.dataframe(pd.DataFrame(rows).T, width="stretch")
        st.caption(next(iter(ev["classification"].values()))["caveat"])
        task = st.selectbox("Confusion matrix", list(ev["classification"]))
        cm = ev["classification"][task]
        fig = go.Figure(go.Heatmap(z=cm["confusion_matrix"], x=cm["labels"], y=cm["labels"], colorscale="Blues",
                                   text=cm["confusion_matrix"], texttemplate="%{text}"))
        fig.update_layout(height=380, xaxis_title="predicted", yaxis_title="true", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        rt = ev["resolution_time"]
        st.markdown("**Resolution-time prediction** (real timestamps, time-based split)")
        st.write({"hours": rt["hours"], "log_hours": rt["log_hours"], "baselines (log hours)": rt["baselines_log_hours"],
                  "P25–P75 interval coverage": rt["p25_p75_interval_coverage"], "n_test": rt["n_test"]})
        fx = ev["fix_accuracy"]
        st.markdown("**Fix-accuracy (reopen risk)** — real Reopen_Time labels")
        _metrics_row(fx, [("ROC_AUC", "ROC-AUC"), ("PR_AUC", "PR-AUC"), ("base_rate", "Base reopen rate"),
                          ("top_decile_lift", "Top-decile lift")])
    with tabs[3]:
        p = ev.get("patterns")
        if p:
            c = p["clustering"]
            _metrics_row(c, [("purity", "Purity"), ("inverse_purity", "Inverse purity"), ("pairwise_precision", "Pairwise P"),
                             ("pairwise_recall", "Pairwise R"), ("NMI", "NMI"), ("ARI", "ARI")])
            st.caption(f"{c['n_clusters']} families · silhouette at selected k {c['silhouette_at_selected_k']} · "
                       f"sampled-pair check {c['sampled_pairs']} · ground truth: {p['ground_truth']}")
            st.markdown("**Ablation — does the enriched fingerprint help?**")
            st.dataframe(pd.DataFrame(p["ablation"]).T[["k_selected", "purity", "inverse_purity", "NMI", "ARI",
                                                         "pairwise_f1"]], width="stretch")
            st.write("Strategy grouping inside families:", p["strategy_grouping"])
            st.write(f"Cross-symptom findings: {len(p['cross_symptom_findings'])}")
        cc = ev["causal_chains"]
        st.markdown("**Causal-chain tagging spot-check** (automated rule conformance)")
        st.write(cc["rule_conformance"])
        st.caption(f"{cc['chains_available']} chains built · {cc['chains_withheld_no_timestamps']} withheld (no timestamps) · "
                   f"tags {cc['tag_distribution']}")
    with tabs[4]:
        n = ev["novelty"]
        st.caption(f"Threshold P(known) = {n['threshold_p_known']} · rule: {n['validation'].get('selection_rule')}")
        df = pd.DataFrame({"validation": n["validation"], "test": n["test"],
                           "baseline (max CE logit) test": n["baseline_single_feature"]["test"]}).T
        st.dataframe(df[["precision", "recall", "f1", "false_novel_rate", "false_known_rate", "n_known", "n_novel"]],
                     width="stretch")
        sw = pd.DataFrame(n["test_sweep"])
        fig = go.Figure([go.Scatter(x=sw["threshold"], y=sw[m], name=m, mode="lines+markers")
                         for m in ("precision", "recall", "false_novel_rate", "false_known_rate")])
        fig.add_vline(x=n["threshold_p_known"], line_dash="dash", line_color="#b42318")
        fig.update_layout(height=320, xaxis_title="threshold on P(known)", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, width="stretch")
        st.write("Test errors:", n["test_errors"])
    with tabs[5]:
        t = ev["troubleshooting"]
        _metrics_row(t, [("resolution_rate", "Resolution rate"), ("first_step_success_rate", "First-step success"),
                         ("average_steps_to_resolution", "Avg steps"), ("escalation_rate", "Escalation rate"),
                         ("clarification_rate", "Clarification rate")])
        st.caption(t["simulated_engineer"])
        st.dataframe(pd.DataFrame(t["by_style"]).T, width="stretch")
    with tabs[6]:
        c = ev["correlation"]
        _metrics_row(c["test"], [("correlation_precision", "Correlation precision"),
                                 ("false_correlation_rate", "False correlation rate"),
                                 ("burst_detection_recall", "Burst recall"),
                                 ("noise_only_false_alert_rate", "Noise-only false alerts")])
        st.write("Detection latency (minutes after first related ticket):", c["test"]["detection_latency_minutes"],
                 "tickets needed:", c["test"]["burst_tickets_needed_to_alert"])
        st.caption(f"Threshold {c['selected_similarity_threshold']} selected by {c['selection']}. {c['stream_design']}")
        st.dataframe(pd.DataFrame(c["validation_sweep"]).T, width="stretch")
    with tabs[7]:
        e = ev["evidence_chain"]
        st.caption(e["definition"])
        st.dataframe(pd.DataFrame({k: v for k, v in e.items() if k != "definition"}).T, width="stretch")
        q = ev["quality_manager"]
        st.markdown("**Knowledge Quality Manager vs. seeded defects**")
        st.dataframe(pd.DataFrame({"low-quality notes": q["low_quality_notes"],
                                   "seeded contradictions": q["seeded_contradictions"]}).T, width="stretch")
        st.write({k: q[k] for k in ("real_source_A_category_conflicts_flagged", "exact_duplicates_flagged",
                                    "near_duplicates_flagged", "mean_score_by_text_provenance")})
    with tabs[8]:
        lat = ev["latency"]
        st.caption(f"Device: {lat['device']}")
        rows = {k: v for k, v in lat["stages_ms"].items() if isinstance(v, dict) and "median" in v}
        st.dataframe(pd.DataFrame(rows).T, width="stretch")
        for k, v in lat["stages_ms"].items():
            if isinstance(v, dict) and "note" in v:
                st.caption(f"{k}: {v['note']}")
