"""Pure metric functions (unit-tested in tests/test_evaluation_metrics.py)."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np


# ------------------------------------------------------------------ ranking
def precision_at_k(rels: list[int], k: int) -> float:
    top = rels[:k]
    return sum(1 for r in top if r > 0) / k if k else 0.0


def recall_at_k(rels: list[int], k: int, n_relevant: int) -> float:
    return sum(1 for r in rels[:k] if r > 0) / n_relevant if n_relevant else 0.0


def hit_at_k(rels: list[int], k: int) -> float:
    return 1.0 if any(r > 0 for r in rels[:k]) else 0.0


def reciprocal_rank(rels: list[int]) -> float:
    for i, r in enumerate(rels, 1):
        if r > 0:
            return 1.0 / i
    return 0.0


def dcg(gains: list[float], k: int) -> float:
    return sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(gains[:k]))


def ndcg_at_k(gains: list[int], k: int, ideal_gains: list[int]) -> float:
    ideal = dcg(sorted(ideal_gains, reverse=True), k)
    return dcg(gains, k) / ideal if ideal > 0 else 0.0


def context_precision(rels: list[int], k: int) -> float:
    """RAGAS context-precision formula (rank-aware) with ground-truth relevance labels:
    Σ_k precision@k · v_k / (number of relevant items in the top K)."""
    top = [1 if r > 0 else 0 for r in rels[:k]]
    n_rel = sum(top)
    if n_rel == 0:
        return 0.0
    return sum(precision_at_k(top, i + 1) * v for i, v in enumerate(top)) / n_rel


# ------------------------------------------------------------------ classification / clustering
def purity(labels_pred: list, labels_true: list) -> float:
    by = {}
    for p, t in zip(labels_pred, labels_true):
        by.setdefault(p, []).append(t)
    return sum(Counter(v).most_common(1)[0][1] for v in by.values()) / len(labels_true)


def pairwise_prf(labels_pred: list, labels_true: list) -> dict:
    """Exact pairwise precision / recall over all pairs (superset of sampled-pair evaluation)."""
    def c2(n: int) -> int:
        return n * (n - 1) // 2

    cont = Counter(zip(labels_pred, labels_true))
    tp = sum(c2(n) for n in cont.values())
    pred_pairs = sum(c2(n) for n in Counter(labels_pred).values())
    true_pairs = sum(c2(n) for n in Counter(labels_true).values())
    p = tp / pred_pairs if pred_pairs else 0.0
    r = tp / true_pairs if true_pairs else 0.0
    return {"pairwise_precision": round(p, 4), "pairwise_recall": round(r, 4),
            "pairwise_f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
            "pairs_evaluated": int(len(labels_true) * (len(labels_true) - 1) // 2)}


def sampled_pairwise_prf(labels_pred: list, labels_true: list, n_pairs: int = 20000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)
    n = len(labels_true)
    i, j = rng.integers(0, n, n_pairs), rng.integers(0, n, n_pairs)
    keep = i != j
    i, j = i[keep], j[keep]
    lp, lt = np.asarray(labels_pred, dtype=object), np.asarray(labels_true, dtype=object)
    same_p, same_t = lp[i] == lp[j], lt[i] == lt[j]
    tp = int((same_p & same_t).sum())
    p = tp / max(1, int(same_p.sum()))
    r = tp / max(1, int(same_t.sum()))
    return {"sampled_pairs": int(len(i)), "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


# ------------------------------------------------------------------ summaries
def summarize(values: list[float]) -> dict:
    a = np.asarray([v for v in values if v is not None], dtype=float)
    if not len(a):
        return {"n": 0}
    return {"n": int(len(a)), "mean": round(float(a.mean()), 4), "median": round(float(np.median(a)), 4),
            "p95": round(float(np.percentile(a, 95)), 4)}


def bootstrap_ci(values: list[float], n_boot: int = 1000, seed: int = 42) -> list[float]:
    a = np.asarray(values, dtype=float)
    if len(a) < 2:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = [a[rng.integers(0, len(a), len(a))].mean() for _ in range(n_boot)]
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]
