"""Phase 9 evaluation suite — every number is computed here by code against the real/merged data.

Relevance ground truth for known queries comes from the generator's scenario / strategy labels
(`gt_scenario`, `gt_strategy`) of the incident a query was written from — never from the system
being evaluated. The source incident is excluded from retrieval (leave-one-out).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from backend.evaluation import metrics as M
from backend.evidence.chain import assemble
from backend.rag.resolution import rank_resolutions
from backend.retrieval.query_understanding import understand
from backend.schemas.retrieval import RetrievalFilters
from backend.services.analysis import analyze_text

log = logging.getLogger(__name__)
K_LIST = [1, 3, 5, 10]


def _gt(store, iid: str) -> tuple:
    rec = store.get(iid) or {}
    return rec.get("gt_scenario"), rec.get("gt_strategy")


def _gains(store, ids: list[str], gt_s: str, gt_st: str) -> list[int]:
    out = []
    for i in ids:
        s, st = _gt(store, i)
        out.append(2 if (s == gt_s and st == gt_st) else (1 if s == gt_s else 0))
    return out


def _rank_metrics(gains: list[int], n_rel: int, ideal: list[int]) -> dict:
    rels = [1 if g > 0 else 0 for g in gains]
    out = {"MRR": M.reciprocal_rank(rels)}
    for k in K_LIST:
        out[f"P@{k}"] = M.precision_at_k(rels, k)
        out[f"R@{k}"] = M.recall_at_k(rels, k, n_rel)
        out[f"Hit@{k}"] = M.hit_at_k(rels, k)
        out[f"nDCG@{k}"] = M.ndcg_at_k(gains, k, ideal)
    return out


# ====================================================================== retrieval
def eval_retrieval(rt, queries: pd.DataFrame) -> dict:
    store = rt.store
    canon = store.records[store.records["canonical"].astype(bool)]
    by_scen = canon.groupby("gt_scenario")["gt_strategy"].apply(list).to_dict()
    known = queries[queries["label"] == "known"]
    configs = ["bm25_only", "semantic_only", "hybrid_rrf", "hybrid_rrf_rerank", "hybrid_rerank_no_query_translation"]
    per_cfg = {c: [] for c in configs}
    styles, timings = [], []
    for q in known.to_dict(orient="records"):
        src, gt_s, gt_st = q["source_incident"], q["gt_scenario"], q["gt_strategy"]
        pool = list(by_scen.get(gt_s, []))
        if store.get(src) and store.get(src).get("canonical"):
            pool.remove(gt_st) if gt_st in pool else None
        n_rel = len(pool)
        ideal = sorted([2 if st == gt_st else 1 for st in pool], reverse=True)
        filt = RetrievalFilters(exclude_incident_ids=[src])
        qu = understand(q["query"], vague_max_tokens=rt.s.clarification_vague_max_tokens)
        # BM25 only
        mask = store.filter_mask(filt, canonical_only=True)
        bm = rt.retriever.bm25.search(qu.expanded_query, n=50, allowed=mask)
        ids = list(dict.fromkeys(store.chunk_incident[store.chunk_pos[c]] for c, _, _ in bm))[:10]
        per_cfg["bm25_only"].append(_rank_metrics(_gains(store, ids, gt_s, gt_st), n_rel, ideal))
        # semantic only
        sem = rt.vectors.query(rt.embedder.embed([qu.expanded_query])[0], n=50,
                               where=store.chroma_where(filt, canonical_only=True))
        ids = list(dict.fromkeys(store.chunk_incident[store.chunk_pos[c]] for c, _, _ in sem))[:10]
        per_cfg["semantic_only"].append(_rank_metrics(_gains(store, ids, gt_s, gt_st), n_rel, ideal))
        # hybrid without / with rerank
        r1 = rt.retriever.search(q["query"], filters=filt, top_k=10, rerank=False, qu=qu)
        per_cfg["hybrid_rrf"].append(_rank_metrics(_gains(store, [r.incident_id for r in r1.results], gt_s, gt_st), n_rel, ideal))
        r2 = rt.retriever.search(q["query"], filters=filt, top_k=10, rerank=True, qu=qu)
        timings.append(r2.timings_ms)
        per_cfg["hybrid_rrf_rerank"].append(_rank_metrics(_gains(store, [r.incident_id for r in r2.results], gt_s, gt_st), n_rel, ideal))
        qu0 = replace(qu, expanded_query=qu.original, technical_concepts=[], matched_phrases=[])
        r3 = rt.retriever.search(q["query"], filters=filt, top_k=10, rerank=True, qu=qu0)
        per_cfg["hybrid_rerank_no_query_translation"].append(
            _rank_metrics(_gains(store, [r.incident_id for r in r3.results], gt_s, gt_st), n_rel, ideal))
        styles.append(q["style"])
    out = {}
    for c, rows in per_cfg.items():
        df = pd.DataFrame(rows)
        out[c] = {k: round(float(v), 4) for k, v in df.mean().items()}
    main = pd.DataFrame(per_cfg["hybrid_rrf_rerank"])
    ci = {m: M.bootstrap_ci(main[m].tolist()) for m in ("MRR", "nDCG@10", "P@5", "Hit@5")}
    main["style"] = styles
    by_style = {st: {k: round(float(v), 4) for k, v in g.drop(columns="style").mean()[["MRR", "P@5", "Hit@5", "nDCG@10"]].items()}
                for st, g in main.groupby("style")}
    return {"n_queries": int(len(known)), "configs": out, "main_config": "hybrid_rrf_rerank",
            "bootstrap_95ci_main": ci, "by_query_style": by_style, "timings": timings,
            "relevance": "graded: 2 = same ground-truth scenario AND resolution strategy as the source incident, "
                         "1 = same scenario; source incident excluded; exact duplicates collapsed (canonical only)",
            "recall_note": "R@K divides by ALL relevant incidents of the scenario (often 40-220), so it is small by "
                           "construction; P@K / Hit@K / MRR / nDCG are the informative ranking metrics."}


# ====================================================================== RAG (retrieval-only mode + optional LLM mode)
def _ragas_nonllm(samples: list[dict]) -> dict:
    """Official RAGAS non-LLM context metrics (string-similarity based) on a subset."""
    try:
        from ragas import SingleTurnSample
        from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall
    except Exception as exc:  # noqa: BLE001
        return {"status": f"ragas unavailable ({exc})"}
    prec_m, rec_m = NonLLMContextPrecisionWithReference(), NonLLMContextRecall()

    async def run():
        p, r = [], []
        for s in samples:
            smp = SingleTurnSample(retrieved_contexts=s["retrieved"], reference_contexts=s["reference"])
            p.append(await prec_m.single_turn_ascore(smp))
            r.append(await rec_m.single_turn_ascore(smp))
        return p, r

    try:
        p, r = asyncio.run(run())
    except Exception as exc:  # noqa: BLE001
        return {"status": f"ragas scoring failed ({exc})"}
    return {"status": "computed", "n": len(samples),
            "non_llm_context_precision_with_reference": round(float(np.mean(p)), 4),
            "non_llm_context_recall": round(float(np.mean(r)), 4),
            "note": "RAGAS non-LLM metrics compare contexts by string similarity (Levenshtein); paraphrased "
                    "notes of the same strategy score low, so these are conservative lexical measures."}


def eval_rag(rt, queries: pd.DataFrame, sidx) -> dict:
    store = rt.store
    known = queries[(queries["label"] == "known") & (queries["split"] == "test")]
    canon = store.records[store.records["canonical"].astype(bool)]
    rows, ragas_samples, stage_t = [], [], []
    for q in known.to_dict(orient="records"):
        src, gt_s, gt_st = q["source_incident"], q["gt_scenario"], q["gt_strategy"]
        b = analyze_text(rt, q["query"], exclude_ids=[src], top_k=10)
        t0 = time.perf_counter()
        ranking = rank_resolutions(b.retrieval.results, sidx, reranked=b.retrieval.mode.reranked,
                                   family=b.families[0] if b.families else None)
        t1 = time.perf_counter()
        assemble(rt, b, ranking)
        t2 = time.perf_counter()
        stage_t.append({**b.timer.timings_ms, "resolution_ranking": (t1 - t0) * 1000,
                        "evidence_chain_assembly": (t2 - t1) * 1000})
        top5 = b.retrieval.results[:5]
        gains = _gains(store, [r.incident_id for r in top5], gt_s, gt_st)
        ctx_prec = M.context_precision(gains, 5)
        cov_s = any(g >= 1 for g in gains)
        cov_st = any(g == 2 for g in gains)
        top = ranking["top"]
        rec_correct = strat_correct = None
        if top:
            sup = [_gt(store, i) for i in top["supporting_incidents"]]
            maj_s = Counter(s for s, _ in sup).most_common(1)[0][0]
            maj_st = Counter(st for _, st in sup).most_common(1)[0][0]
            rec_correct, strat_correct = maj_s == gt_s, (maj_s == gt_s and maj_st == gt_st)
            answer = f"{top['action']}. {top['step']}"
            v = rt.embedder.embed([q["query"], answer, top["step"]])
            rel, extractive = float(v[0] @ v[1]), float(v[1] @ v[2])
        else:
            rel = extractive = None
        rows.append({"context_precision@5": ctx_prec, "context_recall": (cov_s + cov_st) / 2,
                     "family_correct@1": rec_correct, "strategy_correct@1": strat_correct,
                     "answer_relevancy_embedding": rel, "answer_extractive_support": extractive,
                     "confidence": top["confidence"] if top else None, "style": q["style"]})
        if len(ragas_samples) < 60:
            ref = canon[(canon["gt_scenario"] == gt_s) & (canon["gt_strategy"] == gt_st) & (canon["incident_id"] != src)]
            ragas_samples.append({"retrieved": [r.resolution_notes or "" for r in top5],
                                  "reference": ref["resolution_notes"].head(5).tolist() or [""]})
    df = pd.DataFrame(rows)
    conf = df.dropna(subset=["confidence", "strategy_correct@1"])
    calib = None
    if len(conf) > 10:
        bins = pd.cut(conf["confidence"], [0, 0.25, 0.5, 0.75, 1.0], include_lowest=True)
        calib = {str(k): {"n": int(len(g)), "strategy_accuracy": round(float(g["strategy_correct@1"].mean()), 3)}
                 for k, g in conf.groupby(bins, observed=True)}
    return {
        "mode": "retrieval-only (no LLM key configured)",
        "n_queries": int(len(df)),
        "context_precision@5": round(float(df["context_precision@5"].mean()), 4),
        "context_recall": round(float(df["context_recall"].mean()), 4),
        "faithfulness": {"value": 1.0 if df["answer_extractive_support"].dropna().min() > 0.99 else
                         round(float((df["answer_extractive_support"] > 0.9).mean()), 4),
                         "basis": "retrieval-only answers are extractive (the recommended step is copied verbatim from a "
                                  "historical note), so faithfulness is 1.0 by construction; see llm_mode for generated text"},
        "answer_relevancy_embedding": round(float(df["answer_relevancy_embedding"].mean()), 4),
        "family_accuracy@1": round(float(df["family_correct@1"].mean()), 4),
        "resolution_strategy_accuracy@1": round(float(df["strategy_correct@1"].mean()), 4),
        "confidence_vs_accuracy": calib,
        "by_style": {st: {k: round(float(v), 4) for k, v in
                          g[["context_precision@5", "context_recall", "strategy_correct@1"]].astype(float).mean().items()}
                     for st, g in df.groupby("style")},
        "ragas_non_llm": _ragas_nonllm(ragas_samples),
        "ragas_llm_metrics": {"status": "not computed — requires an LLM judge (set LLM_API_KEY); faithfulness / "
                                        "answer relevancy for generated text are measured in llm_mode below"},
        "stage_timings": stage_t,
        "definitions": {
            "context_precision@5": "RAGAS rank-aware formula with ground-truth relevance (same scenario)",
            "context_recall": "share of reference facts {root-cause scenario, resolution strategy} present in the top-5 contexts",
            "resolution_strategy_accuracy@1": "the top recommendation's supporting incidents mostly share the source "
                                              "incident's scenario AND strategy (the fix that actually resolved it)",
        },
    }


def eval_rag_llm(rt, queries: pd.DataFrame, sidx, llm, n: int = 40) -> dict:
    """LLM mode: synthesis + validation with a real LLM, faithfulness judged by an NLI cross-encoder."""
    from sentence_transformers import CrossEncoder

    from backend.rag.synthesis import synthesize, validate

    nli = CrossEncoder("cross-encoder/nli-deberta-v3-small")
    labels = {v.lower(): int(k) for k, v in nli.model.config.id2label.items()}
    ent = labels.get("entailment", 1)
    known = queries[(queries["label"] == "known") & (queries["split"] == "test")].head(n)
    rows = []
    for q in known.to_dict(orient="records"):
        b = analyze_text(rt, q["query"], exclude_ids=[q["source_incident"]], top_k=10)
        ranking = rank_resolutions(b.retrieval.results, sidx, reranked=b.retrieval.mode.reranked,
                                   family=b.families[0] if b.families else None)
        if not ranking["top"]:
            continue
        t = time.perf_counter()
        syn = synthesize(llm, q["query"], ranking["top"])
        gen_ms = (time.perf_counter() - t) * 1000
        if not syn:
            continue
        t = time.perf_counter()
        val = validate(llm, rt.embedder, syn, ranking["top"])
        val_ms = (time.perf_counter() - t) * 1000
        notes = [e["note"] for e in ranking["top"]["evidence"][:5]]
        steps = [s["text"] for s in syn["steps"]]
        pairs = [(nte, st) for st in steps for nte in notes]
        probs = nli.predict(pairs, apply_softmax=True)
        p_ent = np.asarray(probs)[:, ent].reshape(len(steps), len(notes)).max(axis=1)
        v = rt.embedder.embed([q["query"], syn["text"]])
        rows.append({"faithfulness_nli": float((p_ent >= 0.5).mean()), "mean_entailment": float(p_ent.mean()),
                     "answer_relevancy_embedding": float(v[0] @ v[1]),
                     "validator_grounded": float(val["all_grounded"]), "unsupported_steps": val["unsupported_steps"],
                     "llm_generation_ms": gen_ms, "llm_validation_ms": val_ms, "n_steps": len(steps)})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"status": "no synthesis produced"}
    return {"status": "computed", "llm": llm.name, "n": int(len(df)),
            "faithfulness_nli": round(float(df["faithfulness_nli"].mean()), 4),
            "mean_entailment_probability": round(float(df["mean_entailment"].mean()), 4),
            "answer_relevancy_embedding": round(float(df["answer_relevancy_embedding"].mean()), 4),
            "validator_all_grounded_rate": round(float(df["validator_grounded"].mean()), 4),
            "mean_unsupported_steps": round(float(df["unsupported_steps"].mean()), 3),
            "latency_ms": {"llm_generation": M.summarize(df["llm_generation_ms"].tolist()),
                           "llm_validation": M.summarize(df["llm_validation_ms"].tolist())},
            "llm_live_calls": llm.calls, "llm_cache_hits": llm.cache_hits,
            "judge": "cross-encoder/nli-deberta-v3-small entailment (premise = historical note, hypothesis = step); "
                     "a step is faithful if P(entailment) >= 0.5 for at least one supporting note"}


# ====================================================================== patterns / causal chains / QM
def eval_patterns(rt) -> dict:
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    from backend.intelligence.pattern_detection import choose_clusters, feature_matrix
    from backend.intelligence.fingerprinting import Fingerprint
    from backend.knowledge.quality import resolution_detail

    proc = rt.s.processed_dir
    kb = pd.read_parquet(proc / "kb_records.parquet")
    meta = json.loads((proc / "embedding_meta.json").read_text(encoding="utf-8"))
    ids = meta["ids"]
    desc = np.load(proc / "emb_desc.npy")
    res = np.load(proc / "emb_res_masked.npy")
    fps = [Fingerprint.from_dict(rt.patterns.fingerprints[i]) for i in ids]
    gt = kb.set_index("incident_id").loc[ids, "gt_scenario"].tolist()
    pred = [rt.patterns.assign.get(i, "none") for i in ids]
    usable = np.array([resolution_detail(n)[0] > 0.2 for n in kb.set_index("incident_id").loc[ids, "resolution_notes"]],
                      dtype=np.float32)

    def quality(labels) -> dict:
        return {"purity": round(M.purity(labels, gt), 4), "inverse_purity": round(M.purity(gt, labels), 4),
                "NMI": round(float(normalized_mutual_info_score(gt, labels)), 4),
                "ARI": round(float(adjusted_rand_score(gt, labels)), 4), **M.pairwise_prf(labels, gt)}

    full = {"n_clusters": len(set(pred)), **quality(pred), "sampled_pairs": M.sampled_pairwise_prf(pred, gt),
            "silhouette_at_selected_k": rt.patterns.meta["silhouette_sweep"].get(str(rt.patterns.meta["k_selected"]),
                                                                                rt.patterns.meta["silhouette_sweep"].get(rt.patterns.meta["k_selected"]))}
    ablations = {}
    for name, kw in (("text_only", {"use_fingerprint": False, "use_resolution": False}),
                     ("text_plus_resolution", {"use_fingerprint": False, "use_resolution": True})):
        X = feature_matrix(desc, res, fps, usable, **kw)
        lab, k, sweep = choose_clusters(X, seed=rt.s.random_seed)
        ablations[name] = {"k_selected": k, "silhouette": sweep[k], **quality([str(x) for x in lab])}
    ablations["enriched_fingerprint (deployed)"] = {"k_selected": rt.patterns.meta["k_selected"], **quality(pred)}
    # strategy grouping purity inside families (Source B rows only)
    strat = json.loads((proc / "strategies.json").read_text(encoding="utf-8"))["strategy_of"]
    b = kb[(kb["source"] == "B_event_log") & kb["incident_id"].isin(list(strat))]
    s_pred = b["incident_id"].map(strat).tolist()
    s_true = (b["gt_scenario"] + "/" + b["gt_strategy"]).tolist()
    cross = [f.summary()["cross_symptom"] | {"family_id": f.family_id} for f in rt.patterns.families.values()
             if f.cross_symptom]
    rec = [{"family_id": f.family_id, "finding": f.extra.get("recurrence", {}).get("finding")}
           for f in rt.patterns.families.values() if f.extra.get("recurrence", {}).get("finding")]
    return {"clustering": full, "ablation": ablations,
            "strategy_grouping": {"n": len(s_pred), "purity": round(M.purity(s_pred, s_true), 4),
                                  "inverse_purity": round(M.purity(s_true, s_pred), 4)},
            "cross_symptom_findings": cross, "recurrence_findings": rec[:10],
            "ground_truth": "generator scenario labels (Source A: template identity); used only for evaluation"}


def eval_causal_chains(rt) -> dict:
    chains = json.loads((rt.s.processed_dir / "causal_chains.json").read_text(encoding="utf-8"))
    kb = rt.store.records.set_index("incident_id")
    checks = Counter()
    tags = Counter()
    for iid, ch in chains.items():
        if iid not in kb.index:
            continue
        r = kb.loc[iid]
        has_time = pd.notna(r["open_time"]) and pd.notna(r["resolved_time"])
        checks["available_iff_timestamps"] += int(ch["available"] == bool(has_time))
        links = ch["links"] or ch["facts"]
        for l in links:
            tags[l["tag"]] += 1
            if l["stage"] == "symptom":
                ok = (l["tag"] == "inferred") == (r["description_source"] == "synthetic")
                checks["symptom_tag_matches_text_provenance"] += int(ok)
                checks["symptom_total"] += 1
            if l["stage"] == "outcome":
                checks["outcome_observed"] += int(l["tag"] == "observed")
                checks["outcome_total"] += 1
            if l["stage"] == "trigger" and l["tag"] == "observed":
                checks["observed_trigger_has_related_change"] += int(pd.notna(r["related_change"]) and str(r["related_change"]) not in ("None", "nan"))
                checks["observed_trigger_total"] += 1
    n = len(chains)
    return {
        "incidents": n, "chains_available": int(sum(c["available"] for c in chains.values())),
        "chains_withheld_no_timestamps": int(sum(not c["available"] for c in chains.values())),
        "tag_distribution": dict(tags),
        "rule_conformance": {
            "available_iff_timestamps": round(checks["available_iff_timestamps"] / n, 4),
            "symptom_tag_matches_text_provenance": round(checks["symptom_tag_matches_text_provenance"] / max(1, checks["symptom_total"]), 4),
            "outcome_links_observed": round(checks["outcome_observed"] / max(1, checks["outcome_total"]), 4),
            "observed_triggers_backed_by_related_change": round(checks["observed_trigger_has_related_change"] / max(1, checks["observed_trigger_total"]), 4),
        },
        "example": next((c for c in chains.values() if c["available"] and len(c["links"]) >= 5), None),
    }


def eval_quality_manager(rt) -> dict:
    kb = rt.store.records
    flags = kb["quality_flags"].map(list)

    def has(f):
        return flags.map(lambda x: f in x)

    def prf(pred, true):
        tp = int((pred & true).sum())
        p = tp / max(1, int(pred.sum()))
        r = tp / max(1, int(true.sum()))
        return {"flagged": int(pred.sum()), "seeded": int(true.sum()), "true_positives": tp,
                "precision": round(p, 4), "recall": round(r, 4)}

    low_true = kb["gt_note_quality"] == "low"
    con_true = kb["gt_seeded_defect"] == "contradiction"
    return {
        "low_quality_notes": prf(has("generic_resolution") | has("empty_resolution"), low_true),
        "seeded_contradictions": prf(has("closure_note_conflict") | has("resolution_inconsistent_with_similar"), con_true),
        "real_source_A_category_conflicts_flagged": int(has("category_text_conflict").sum()),
        "exact_duplicates_flagged": int(has("exact_duplicate").sum()),
        "near_duplicates_flagged": int(has("near_duplicate").sum()),
        "tiers": kb["quality_tier"].value_counts().to_dict(),
        "mean_score_by_text_provenance": kb.groupby("description_source")["quality_score"].mean().round(4).to_dict(),
    }


# ====================================================================== novelty (from calibration)
def eval_novelty(rt) -> dict:
    r = json.loads((rt.s.evaluation_dir / "novelty_results.json").read_text(encoding="utf-8"))
    n = r["novelty"]
    return {"threshold_p_known": n["threshold_p_known"], "weights": n["model_weights"],
            "validation": n["validation"], "test": n["test"], "test_by_style": n["test_by_style"],
            "baseline_single_feature": n["baseline_single_feature"], "test_sweep": n["test_sweep"],
            "test_errors": [d for d in n["test_details"] if (d["label"] == "novel") != (d["predicted"] == "novel")],
            "platt": r["platt"]}


# ====================================================================== troubleshooting simulation
def eval_troubleshooting(rt, queries: pd.DataFrame, sidx, n: int | None = None) -> dict:
    from backend.troubleshooting.session import TroubleshootingService

    ts = TroubleshootingService(rt, sidx, escalation_builder=lambda sess, reason: {"reason": reason, "tier": "sim"})
    known = queries[(queries["label"] == "known") & (queries["split"] == "test")]
    if n:
        known = known.head(n)
    rows = []
    for q in known.to_dict(orient="records"):
        gt_s, gt_st, src = q["gt_scenario"], q["gt_strategy"], q["source_incident"]
        src_fp = rt.patterns.fingerprint_of(src)
        view = ts.start(q["query"], exclude_ids=[src])
        steps = clar = 0
        first_ok = None
        for _ in range(8):  # the source incident is excluded from the session's retrieval (leave-one-out)
            if view["status"] == "awaiting_clarification":
                clar += 1
                f = view["clarification"]["field"]
                val = src_fp.values.get(f) if src_fp else None
                view = ts.clarify(view["session_id"], answer=val) if val and val != "Unknown" else \
                    ts.clarify(view["session_id"], declined=True)
                continue
            if view["status"] != "active":
                break
            cs = view["current_step"]
            steps += 1
            gts = [_gt(rt.store, i) for i in cs["supporting_incidents"]]
            maj = Counter(gts).most_common(1)[0][0]
            worked = maj == (gt_s, gt_st)
            if first_ok is None:
                first_ok = worked
            view = ts.respond(view["session_id"], cs["attempt_id"], "WORKED" if worked else "FAILED")
        rows.append({"status": view["status"], "steps": steps, "clarifications": clar,
                     "first_step_success": bool(first_ok), "style": q["style"]})
    df = pd.DataFrame(rows)
    res = df[df["status"] == "resolved"]
    return {
        "n_sessions": int(len(df)),
        "resolution_rate": round(float((df["status"] == "resolved").mean()), 4),
        "first_step_success_rate": round(float(df["first_step_success"].mean()), 4),
        "average_steps_to_resolution": round(float(res["steps"].mean()), 3) if len(res) else None,
        "escalation_rate": round(float(df["status"].isin(["escalated", "escalation_requested"]).mean()), 4),
        "novel_route_rate": round(float((df["status"] == "novel").mean()), 4),
        "clarification_rate": round(float((df["clarifications"] > 0).mean()), 4),
        "max_clarifications_in_a_session": int(df["clarifications"].max()),
        "by_style": {st: {"resolution_rate": round(float((g["status"] == "resolved").mean()), 3),
                          "avg_steps": round(float(g["steps"].mean()), 2)} for st, g in df.groupby("style")},
        "simulated_engineer": "a step WORKS iff the majority (scenario, strategy) of its supporting incidents equals the "
                              "source incident's ground truth; clarifying questions are answered from the source "
                              "incident's fingerprint when known, otherwise declined",
        "round_cap": rt.s.troubleshooting_max_rounds,
    }


# ====================================================================== live correlation
def eval_correlation(rt, queries: pd.DataFrame, seed: int = 42) -> dict:
    from backend.intelligence.correlation import LiveCorrelator

    rng = np.random.default_rng(seed)
    known = queries[queries["label"] == "known"].reset_index(drop=True)
    cache = {}
    for q in known.to_dict(orient="records"):
        b = analyze_text(rt, q["query"], exclude_ids=[q["source_incident"]], top_k=10)
        cache[q["query"]] = SimpleNamespace(fingerprint=b.fingerprint, families=b.families, novelty=b.novelty,
                                            emb=rt.embedder.embed([q["query"]])[0])
    emb = SimpleNamespace(embed=lambda texts: np.vstack([cache[t].emb for t in texts]))

    def streams(split: str) -> list[list[dict]]:
        pool = known[known["split"] == split]
        by_s = {s: g.to_dict(orient="records") for s, g in pool.groupby("gt_scenario")}
        scen = [s for s, g in by_s.items() if len(g) >= 3]
        out = []
        for s in scen:
            burst = [dict(x, t=m, role="burst") for x, m in zip(rng.permutation(by_s[s])[:3], (0, 4, 9))]
            others = [o for o in by_s if o != s]
            noise = [dict(rng.permutation(by_s[o])[0], t=float(rng.uniform(0, 30)), role="noise")
                     for o in rng.permutation(others)[:3]]
            out.append(sorted(burst + noise, key=lambda e: e["t"]))
        for _ in range(len(scen) // 2):  # noise-only streams (no ongoing incident)
            picks = rng.permutation(list(by_s))[:6]
            out.append(sorted([dict(rng.permutation(by_s[o])[0], t=float(rng.uniform(0, 30)), role="noise") for o in picks],
                              key=lambda e: e["t"]))
        return out

    def run(stream_set, thr: float) -> dict:
        bursts = detected = alerts = pure = noise_streams = noise_alerts = 0
        lat_min, lat_events = [], []
        for st in stream_set:
            corr = LiveCorrelator(rt.s, rt.patterns, rt.fingerprinter, emb, persist=False, similarity_threshold=thr,
                                  analyzer=lambda text: cache[text])
            t0 = datetime(2026, 1, 1, 9, 0)
            first_alert, n_seen = None, 0
            has_burst = any(e["role"] == "burst" for e in st)
            for e in st:
                r = corr.ingest(e["query"], received_at=t0 + timedelta(minutes=e["t"]),
                                incident_id=f"{e['query_id']}", scenario_tag=e["role"])
                if e["role"] == "burst":
                    n_seen += 1
                a = r["alert"]
                if a and first_alert is None and has_burst:
                    burst_ids = {x["query_id"] for x in st if x["role"] == "burst"}
                    if len(burst_ids & set(a["members"])) >= 2:
                        first_alert = (e["t"], n_seen)
            role = {e["query_id"]: (e["gt_scenario"], e["role"]) for e in st}
            for a in corr.alerts.values():
                alerts += 1
                scen = {role[m][0] for m in a.members}
                pure += int(len(scen) == 1)
            if has_burst:
                bursts += 1
                if first_alert:
                    detected += 1
                    lat_min.append(first_alert[0])
                    lat_events.append(first_alert[1])
            else:
                noise_streams += 1
                noise_alerts += int(len(corr.alerts) > 0)
        prec = pure / alerts if alerts else 0.0
        rec = detected / bursts if bursts else 0.0
        return {"bursts": bursts, "burst_detection_recall": round(rec, 4), "alerts": alerts,
                "correlation_precision": round(prec, 4), "false_correlation_rate": round(1 - prec, 4) if alerts else 0.0,
                "noise_only_streams": noise_streams,
                "noise_only_false_alert_rate": round(noise_alerts / noise_streams, 4) if noise_streams else 0.0,
                "detection_latency_minutes": M.summarize(lat_min),
                "burst_tickets_needed_to_alert": M.summarize(lat_events),
                "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0}

    val_streams, test_streams = streams("validation"), streams("test")
    sweep = {round(t, 2): run(val_streams, t) for t in np.arange(0.4, 0.95, 0.05)}
    best_thr = max(sweep, key=lambda t: (sweep[t]["f1"], -sweep[t]["noise_only_false_alert_rate"], t))
    test = run(test_streams, best_thr)
    return {"selected_similarity_threshold": best_thr, "selection": "max F1(precision, burst recall) on validation streams",
            "validation_sweep": {str(k): {m: v[m] for m in ("correlation_precision", "burst_detection_recall", "f1",
                                                            "noise_only_false_alert_rate")} for k, v in sweep.items()},
            "test": test, "window_minutes": rt.s.correlation_window_minutes,
            "min_incidents": rt.s.correlation_min_incidents,
            "stream_design": "per scenario: 3 differently-worded tickets at t=0/4/9 min + 3 unrelated tickets at random "
                             "times in a 30-min window; plus noise-only streams of 6 unrelated tickets"}


# ====================================================================== evidence chain
def eval_evidence_chain(rt, queries: pd.DataFrame, sidx) -> dict:
    test = queries[queries["split"] == "test"]
    rows = []
    for q in test.to_dict(orient="records"):
        b = analyze_text(rt, q["query"], exclude_ids=[q["source_incident"]] if q["label"] == "known" else None)
        ranking = rank_resolutions(b.retrieval.results, sidx, reranked=b.retrieval.mode.reranked,
                                   family=b.families[0] if b.families else None)
        ch = assemble(rt, b, ranking)
        rows.append({"label": q["label"], "complete_core": ch["completeness"]["complete_core"],
                     "ratio": ch["completeness"]["ratio"], "insufficient": ch["completeness"]["insufficient"],
                     "novel_verdict": b.novelty.get("is_novel")})
    df = pd.DataFrame(rows)
    out = {}
    for label, g in df.groupby("label"):
        ins = Counter(f for lst in g["insufficient"] for f in lst)
        out[label] = {"n": int(len(g)), "complete_core_rate": round(float(g["complete_core"].mean()), 4),
                      "mean_completeness": round(float(g["ratio"].mean()), 4),
                      "insufficient_field_counts": dict(ins)}
    return {**out, "definition": "a recommendation's evidence object is 'complete' when family match, root-cause "
                                 "evidence and resolution evidence are all populated from real data (not "
                                 "'insufficient evidence'); evidence-strength values are counted separately"}


# ====================================================================== latency
def eval_latency(retrieval_timings: list[dict], rag_timings: list[dict], llm_latency: dict | None, device: str) -> dict:
    """Per-stage latency of the full analysis pipeline (query processing → … → evidence chain)."""
    stages: dict[str, list] = {}
    for t in rag_timings:
        for k, v in t.items():
            stages.setdefault(k, []).append(v)
    out = {k: M.summarize(v) for k, v in stages.items()}
    out["end_to_end_analysis_pipeline"] = M.summarize([sum(t.values()) for t in rag_timings])
    out["hybrid_retrieval_only"] = M.summarize([sum(t.values()) for t in retrieval_timings])
    if llm_latency:
        out.update(llm_latency)  # keys are already llm_generation / llm_validation
    else:
        out["llm_generation"] = {"note": "0 ms — retrieval-only mode (no LLM configured)"}
    return {"device": device, "stages_ms": out}
