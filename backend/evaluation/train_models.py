"""Train and evaluate the triage models on real data (Phase 7 training, Phase 9 metrics)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix, f1_score, mean_absolute_error,
    mean_squared_error, precision_recall_fscore_support, r2_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

from backend.services.triage import OPEN_FEATURES, RESOLVE_FEATURES, FrameEncoder, open_frame, resolve_frame

SEED = 42


def train_resolution_time(unified: pd.DataFrame) -> dict:
    df = unified[(unified["source"] == "B_event_log") & unified["resolution_hours"].notna()
                 & (unified["resolution_hours"] >= 0)].sort_values("open_time")
    X, y = open_frame(df), np.log1p(df["resolution_hours"].to_numpy())
    cut = int(len(df) * 0.8)  # time-based split: train on the earlier 80%, test on the latest 20%
    enc = FrameEncoder(["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type"],
                       ["open_hour", "open_weekday"]).fit(X.iloc[:cut])
    Xtr, Xte = enc.transform(X.iloc[:cut]), enc.transform(X.iloc[cut:])
    models = {}
    for name, q in (("median", 0.5), ("q25", 0.25), ("q75", 0.75)):
        models[name] = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=300, learning_rate=0.05,
                                                     categorical_features=enc.categorical_mask,
                                                     random_state=SEED).fit(Xtr, y[:cut])
    pred_log = models["median"].predict(Xte)
    yt = y[cut:]
    hours_true, hours_pred = np.expm1(yt), np.expm1(pred_log)
    base = np.full_like(yt, np.median(y[:cut]))
    sub_med = pd.Series(y[:cut]).groupby(X.iloc[:cut]["ci_subcategory"].to_numpy()).median()
    base_sub = X.iloc[cut:]["ci_subcategory"].map(sub_med).fillna(np.median(y[:cut])).to_numpy()
    lo, hi = models["q25"].predict(Xte), models["q75"].predict(Xte)
    metrics = {
        "n_train": int(cut), "n_test": int(len(df) - cut), "split": "time-based (latest 20% as test)",
        "target": "resolution hours = Resolved_Time - Open_Time (recomputed from timestamps)",
        "features": OPEN_FEATURES,
        "hours": {"MAE": round(float(mean_absolute_error(hours_true, hours_pred)), 2),
                  "RMSE": round(float(np.sqrt(mean_squared_error(hours_true, hours_pred))), 2),
                  "R2": round(float(r2_score(hours_true, hours_pred)), 4),
                  "median_absolute_error": round(float(np.median(np.abs(hours_true - hours_pred))), 2)},
        "log_hours": {"MAE": round(float(mean_absolute_error(yt, pred_log)), 4),
                      "RMSE": round(float(np.sqrt(mean_squared_error(yt, pred_log))), 4),
                      "R2": round(float(r2_score(yt, pred_log)), 4)},
        "baselines_log_hours": {
            "global_median_MAE": round(float(mean_absolute_error(yt, base)), 4),
            "global_median_R2": round(float(r2_score(yt, base)), 4),
            "ci_subcategory_median_MAE": round(float(mean_absolute_error(yt, base_sub)), 4),
            "ci_subcategory_median_R2": round(float(r2_score(yt, base_sub)), 4)},
        "p25_p75_interval_coverage": round(float(np.mean((yt >= lo) & (yt <= hi))), 4),
    }
    return {"encoder": enc, **models, "test_metrics": metrics}


def train_fix_accuracy(unified: pd.DataFrame) -> dict:
    df = unified[(unified["source"] == "B_event_log") & unified["resolution_hours"].notna()].copy()
    X, y = resolve_frame(df), df["reopened"].astype(int).to_numpy()
    Xtr_df, Xte_df, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    enc = FrameEncoder(["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type", "closure_class"],
                       ["log_resolution_hours", "no_of_reassignments"]).fit(Xtr_df)
    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, categorical_features=enc.categorical_mask,
                                           random_state=SEED).fit(enc.transform(Xtr_df), ytr)
    p = model.predict_proba(enc.transform(Xte_df))[:, 1]
    top = np.argsort(-p)[: max(1, len(p) // 10)]
    return {"encoder": enc, "model": model, "base_rate": round(float(y.mean()), 4), "test_metrics": {
        "n_train": int(len(ytr)), "n_test": int(len(yte)), "split": "stratified random 80/20",
        "target": "reopened (Reopen_Time present) - real label", "features": RESOLVE_FEATURES,
        "ROC_AUC": round(float(roc_auc_score(yte, p)), 4),
        "PR_AUC": round(float(average_precision_score(yte, p)), 4),
        "brier": round(float(brier_score_loss(yte, p)), 4),
        "base_rate": round(float(yte.mean()), 4),
        "top_decile_reopen_rate": round(float(yte[top].mean()), 4),
        "top_decile_lift": round(float(yte[top].mean() / max(yte.mean(), 1e-9)), 2),
    }}


def train_text_classifiers(kb: pd.DataFrame) -> tuple[dict, dict]:
    text = (kb["title"].fillna("") + ". " + kb["description"].fillna("")).to_numpy()
    tasks = {"category": kb["category"].astype(str).to_numpy()}
    b = (kb["source"] == "B_event_log").to_numpy()
    for f in ("priority", "impact", "urgency"):
        lab = kb[f].astype(str).to_numpy()
        tasks[f] = np.where(b & (lab != "Not Set"), lab, None)
    clfs, metrics = {}, {}
    for name, labels in tasks.items():
        mask = pd.notna(labels)
        X, y = text[mask], labels[mask].astype(str)
        counts = pd.Series(y).value_counts()
        keep = np.isin(y, counts[counts >= 5].index)  # classes with < 5 examples cannot be evaluated
        X, y = X[keep], y[keep]
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=SEED, stratify=y)
        clf = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                            LogisticRegression(max_iter=3000, class_weight="balanced"))
        clf.fit(Xtr, ytr)
        pred = clf.predict(Xte)
        labs = sorted(set(y))
        p, r, f, s = precision_recall_fscore_support(yte, pred, labels=labs, zero_division=0)
        majority = counts.idxmax()
        metrics[name] = {
            "n_train": int(len(ytr)), "n_test": int(len(yte)),
            "accuracy": round(float(accuracy_score(yte, pred)), 4),
            "macro_precision": round(float(p.mean()), 4), "macro_recall": round(float(r.mean()), 4),
            "macro_f1": round(float(f1_score(yte, pred, average="macro")), 4),
            "weighted_f1": round(float(f1_score(yte, pred, average="weighted")), 4),
            "majority_class_baseline_accuracy": round(float((yte == majority).mean()), 4),
            "labels": labs, "confusion_matrix": confusion_matrix(yte, pred, labels=labs).tolist(),
            "per_class": {l: {"precision": round(float(a), 3), "recall": round(float(bb), 3), "f1": round(float(c), 3),
                              "support": int(d)} for l, a, bb, c, d in zip(labs, p, r, f, s)},
            "label_provenance": "category: derived (CI_Subcat mapping / corrected text category); "
                                "priority/impact/urgency: original Source B fields",
            "caveat": "Source B text is synthetic and was conditioned on these fields; scores are optimistic "
                      "relative to real free text.",
        }
        clfs[name] = clf
    return clfs, metrics


def train_all(unified: pd.DataFrame, kb: pd.DataFrame) -> dict:
    clfs, tmetrics = train_text_classifiers(kb)
    return {"resolution_time": train_resolution_time(unified), "fix_accuracy": train_fix_accuracy(unified),
            "text_classifiers": clfs, "text_classifier_metrics": tmetrics}
