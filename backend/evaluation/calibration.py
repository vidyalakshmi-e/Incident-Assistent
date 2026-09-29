"""Calibration on the VALIDATION split (Phase 5):

1. Cross-encoder Platt scaling: P(relevant | logit), where "relevant" = the retrieved incident
   belongs to the query's ground-truth scenario. Turns raw logits into a calibrated confidence.
2. Novelty model: logistic regression over the four novelty signals + the P(known) threshold that
   maximises F1 for the NOVEL class on validation (ties → lower false-novel rate).

Both are written to data/evaluation/calibration.json. Metrics are then reported on the TEST split.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from backend.intelligence.novelty import FEATURES, NoveltyDetector, NoveltyModel, novelty_features
from backend.services.analysis import analyze_text


def _run(rt, df: pd.DataFrame) -> list[dict]:
    rows = []
    for r in df.to_dict(orient="records"):
        excl = [r["source_incident"]] if r["label"] == "known" else None
        b = analyze_text(rt, r["query"], exclude_ids=excl, top_k=10)
        gt_of = {x.incident_id: rt.store.get(x.incident_id).get("gt_scenario") for x in b.retrieval.results}
        rows.append({**r, "bundle": b, "features": novelty_features(b.retrieval, b.families, b.fingerprint),
                     "pairs": [(x.scores.rerank_logit, gt_of[x.incident_id] == r["gt_scenario"])
                               for x in b.retrieval.results if x.scores.rerank_logit is not None]})
    return rows


def novelty_metrics(y_novel: np.ndarray, pred_novel: np.ndarray) -> dict:
    tp = int((y_novel & pred_novel).sum())
    fp = int((~y_novel & pred_novel).sum())
    fn = int((y_novel & ~pred_novel).sum())
    tn = int((~y_novel & ~pred_novel).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0,
            "false_novel_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
            "false_known_rate": round(fn / (fn + tp), 4) if fn + tp else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n_known": fp + tn, "n_novel": tp + fn}


MAX_FALSE_NOVEL_RATE = 0.02  # operating constraint: ≤ 2% of known incidents may be flagged novel


def choose_threshold(p_known: np.ndarray, y_novel: np.ndarray,
                     max_false_novel: float = MAX_FALSE_NOVEL_RATE) -> tuple[float, dict]:
    """Operating-point selection on VALIDATION: the largest threshold (→ highest novel recall) whose
    false-novel rate on known incidents stays ≤ `max_false_novel`. The constraint is estimated on
    the large known class (≈130 queries), which is far more stable than optimising F1 on ~20 novel
    probes. The threshold is placed half-way between the last admissible score and the next one."""
    known_scores = np.sort(p_known[~y_novel])
    allowed = int(np.floor(max_false_novel * len(known_scores)))  # known queries we may flag
    upper = known_scores[allowed] if allowed < len(known_scores) else 1.0
    lower = known_scores[allowed - 1] if allowed >= 1 else 0.0
    thr = float((lower + upper) / 2) if allowed >= 1 else float(upper) - 1e-6
    return thr, {**novelty_metrics(y_novel, p_known < thr),
                 "selection_rule": f"max novel recall s.t. false-novel rate ≤ {max_false_novel:.0%} (validation)"}


def calibrate(rt, eval_df: pd.DataFrame, out_path: Path) -> dict:
    val = eval_df[eval_df["split"] == "validation"]
    test = eval_df[eval_df["split"] == "test"]

    # ---- 1. cross-encoder Platt scaling (known validation queries)
    val_rows = _run(rt, val)
    pairs = [p for r in val_rows if r["label"] == "known" for p in r["pairs"]]
    X = np.array([[p[0]] for p in pairs])
    y = np.array([int(p[1]) for p in pairs])
    platt = LogisticRegression().fit(X, y)
    calib = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    calib.update({
        "ce_platt_a": {"value": float(platt.coef_[0][0]), "fitted_on": f"{len(pairs)} (query, result) pairs, validation split"},
        "ce_platt_b": {"value": float(platt.intercept_[0])},
    })
    calib.pop("novelty", None)
    out_path.write_text(json.dumps(calib, indent=2), encoding="utf-8")

    # ---- 2. novelty model on validation (re-run so family ranking uses calibrated confidences)
    rt.novelty = NoveltyDetector(rt.s, model=None)
    val_rows = _run(rt, val)
    Fv = np.array([[r["features"][f] for f in FEATURES] for r in val_rows])
    yv = np.array([r["label"] == "novel" for r in val_rows])
    means, stds = Fv.mean(0), Fv.std(0) + 1e-6
    lr = LogisticRegression(class_weight="balanced").fit((Fv - means) / stds, (~yv).astype(int))
    model = NoveltyModel(lr.coef_[0].tolist(), float(lr.intercept_[0]), means.tolist(), stds.tolist(), 0.5)
    pv = np.array([model.p_known(r["features"]) for r in val_rows])
    thr, val_metrics = choose_threshold(pv, yv)
    model.threshold = thr

    # single-feature baseline for transparency (threshold on max cross-encoder logit)
    lv = Fv[:, 0]
    base_thr, base_val = choose_threshold(1 / (1 + np.exp(-lv)), yv)

    calib["novelty"] = {"weights": model.weights, "bias": model.bias, "means": model.means, "stds": model.stds,
                        "threshold": thr, "features": FEATURES, "value": thr,
                        "fitted_on": f"validation split: {int((~yv).sum())} known, {int(yv.sum())} novel",
                        "selection_rule": val_metrics["selection_rule"],
                        "created": datetime.utcnow().isoformat()}
    out_path.write_text(json.dumps(calib, indent=2), encoding="utf-8")
    rt.novelty = NoveltyDetector(rt.s, model=model)

    # ---- 3. held-out test
    test_rows = _run(rt, test)
    Ft = np.array([[r["features"][f] for f in FEATURES] for r in test_rows])
    yt = np.array([r["label"] == "novel" for r in test_rows])
    pt = np.array([model.p_known(r["features"]) for r in test_rows])
    test_metrics = novelty_metrics(yt, pt < thr)
    base_test = novelty_metrics(yt, 1 / (1 + np.exp(-Ft[:, 0])) < base_thr)
    styles = pd.Series([r["style"] for r in test_rows])
    per_style = {st: {"n": int((styles == st).sum()),
                      "flagged_novel": int(((pt < thr) & (styles == st).to_numpy()).sum())}
                 for st in styles.unique()}
    # threshold sweep on test (for the evaluation page's curve)
    sweep = [{"threshold": round(float(t), 3), **novelty_metrics(yt, pt < t)} for t in np.linspace(0.05, 0.95, 19)]
    details = [{"query_id": r["query_id"], "query": r["query"], "label": r["label"], "style": r["style"],
                "p_known": round(float(p), 4), "predicted": "novel" if p < thr else "known",
                "features": {k: round(v, 4) for k, v in r["features"].items()}}
               for r, p in zip(test_rows, pt)]
    return {
        "platt": {"a": calib["ce_platt_a"]["value"], "b": calib["ce_platt_b"]["value"], "pairs": len(pairs),
                  "positive_rate": round(float(y.mean()), 4)},
        "novelty": {"threshold_p_known": round(thr, 4), "model_weights": dict(zip(FEATURES, np.round(model.weights, 3).tolist())),
                    "validation": val_metrics, "test": test_metrics, "test_by_style": per_style,
                    "baseline_single_feature": {"feature": "max_relevance_logit", "validation": base_val, "test": base_test},
                    "test_sweep": sweep, "test_details": details},
    }
