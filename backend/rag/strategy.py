"""Resolution Strategy Intelligence (MAJOR DIFFERENTIATOR 4).

For each incident family, the historically observed resolution approaches are grouped into
strategies by clustering the (entity-masked) resolution-note embeddings of the family members.
Low-quality notes ("closed", "fixed") describe no strategy and are counted separately.

Outcome statistics (reopen rate with a Wilson 95% interval, median resolution time, mean
reassignments) are computed ONLY from members with real outcome fields (Reopen_Time,
timestamps, No_of_Reassignments) and ONLY when at least MIN_OUTCOME_N such members exist.
Otherwise the strategy is shown as "historical resolution observed for this pattern" with no
percentages. The strategy *wording* for Source B rows is synthetic (flagged); the outcome fields
are original.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from backend.knowledge.quality import ACTION, resolution_detail

MIN_OUTCOME_N = 20
MAX_STRATEGIES = 5


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)


CLAUSE_SPLIT = re.compile(r"(?<=[.;:])\s+|,\s+(?:and\s+)?|\s+by\s+|\s+(?:and|then)\s+(?=\w+(?:ed|ing)\b)|\.\s*$")


def action_clauses(note: str) -> list[str]:
    """Clauses of a resolution note that describe an action (root-cause-only clauses are dropped).

    'The memory leak ... was resolved by restarting the application service.' → ['restarting the
    application service']."""
    parts = [p.strip(" .;,:") for p in CLAUSE_SPLIT.split(str(note or "")) if p and p.strip(" .;,:")]
    return [p for p in parts if ACTION.search(p)]


def action_text(note: str) -> str:
    acts = action_clauses(note)
    return ". ".join(acts) if acts else str(note or "")


_CI = re.compile(r"\b[A-Z]{2,4}\d{5,6}\b")


def normalized_action(note: str) -> str:
    """Action clauses with CI and service names masked — used to compare *what was done*."""
    from backend.knowledge.quality import mask_entities

    return _CI.sub("the system", mask_entities(action_text(note), None))


def action_summary(note: str) -> str:
    acts = action_clauses(note)
    if acts:
        a = acts[0]
        return (a[0].upper() + a[1:])[:160]
    sents = [s.strip() for s in str(note).replace(";", ".").split(".") if s.strip()]
    return sents[0][:160] if sents else str(note)[:160]


ACTION_DISTANCE = 0.6  # cosine distance on masked action clauses (spot check: restart paraphrases
# 0.68-0.73 similar, different actions 0.08-0.12), so 0.6 distance (0.4 similarity) separates them


def _choose_k(E: np.ndarray) -> np.ndarray:
    """Group notes by *action*: average-linkage clustering with a distance threshold, then fold
    groups smaller than max(3, 5% of the family) into their nearest larger group."""
    n = len(E)
    if n < 4:
        return np.zeros(n, dtype=int)
    lab = AgglomerativeClustering(n_clusters=None, distance_threshold=ACTION_DISTANCE, metric="cosine",
                                  linkage="average").fit_predict(E)
    min_size = max(3, int(0.05 * n))
    sizes = {l: int((lab == l).sum()) for l in set(lab)}
    big = [l for l, c in sorted(sizes.items(), key=lambda t: -t[1]) if c >= min_size][:MAX_STRATEGIES]
    if not big:
        return np.zeros(n, dtype=int)
    cents = {l: E[lab == l].mean(0) for l in big}
    out = np.array([l if l in cents else max(cents, key=lambda b: float(cents[b] @ E[i]))
                    for i, l in enumerate(lab)])
    return out


def outcome_stats(rows: pd.DataFrame) -> dict:
    with_outcome = rows[rows["reopened_source"] != "missing"]
    n = int(len(with_outcome))
    stats = {"n_with_outcome": n, "stats_supported": n >= MIN_OUTCOME_N}
    if n >= MIN_OUTCOME_N:
        k = int(with_outcome["reopened"].astype(bool).sum())
        lo, hi = wilson(k, n)
        rh = with_outcome["resolution_hours"].dropna()
        stats.update({
            "reopen_rate": round(k / n, 4), "reopen_ci_low": lo, "reopen_ci_high": hi,
            "median_resolution_hours": round(float(rh.median()), 2) if len(rh) else None,
            "mean_reassignments": round(float(with_outcome["no_of_reassignments"].mean()), 2),
            "basis": f"{n} incidents with real Reopen_Time / timestamps / reassignment fields",
        })
    else:
        stats["basis"] = (f"only {n} member(s) have real outcome data (< {MIN_OUTCOME_N}); "
                          "historical resolutions observed for this pattern — no success statistics shown")
    return stats


class StrategyIndex:
    """Runtime access to the strategies built offline (data/processed/strategies.json)."""

    def __init__(self, strategies: list[dict], strategy_of: dict[str, str]):
        self.by_key = {s["strategy_key"]: s for s in strategies}
        self.strategy_of = dict(strategy_of)
        self.by_family: dict[str, list[dict]] = {}
        for s in strategies:
            self.by_family.setdefault(s["pattern_id"], []).append(s)

    @classmethod
    def load(cls, processed_dir) -> "StrategyIndex":
        import json
        from pathlib import Path

        d = json.loads((Path(processed_dir) / "strategies.json").read_text(encoding="utf-8"))
        return cls(d["strategies"], d["strategy_of"])

    def key_for(self, incident_id: str) -> str:
        return self.strategy_of.get(incident_id, f"INC:{incident_id}")

    def panel(self, family_id: str | None) -> list[dict]:
        if not family_id:
            return []
        out = []
        for s in sorted(self.by_family.get(family_id, []), key=lambda x: -x["n_incidents"]):
            item = {k: v for k, v in s.items() if k != "centroid"}
            item["kind"] = "observed historical resolution"
            if not s["stats_supported"]:
                for k in ("reopen_rate", "reopen_ci_low", "reopen_ci_high", "median_resolution_hours", "mean_reassignments"):
                    item.pop(k, None)
            out.append(item)
        return out


def build_family_strategies(fid: str, members: pd.DataFrame, res_emb: dict[str, np.ndarray]) -> tuple[list[dict], dict[str, str]]:
    """Return (strategies, incident_id → strategy_key)."""
    usable_mask = members["resolution_notes"].map(lambda n: resolution_detail(n)[0] > 0.2)
    usable = members[usable_mask].reset_index(drop=True)
    undocumented = int((~usable_mask).sum())
    strategy_of: dict[str, str] = {}
    if usable.empty:
        return [], strategy_of
    E = np.vstack([res_emb[i] for i in usable["incident_id"]])
    labels = _choose_k(E)
    strategies = []
    for s_i, lab in enumerate(sorted(set(labels), key=lambda l: -(labels == l).sum())):
        idx = np.where(labels == lab)[0]
        sub = usable.iloc[idx]
        c = E[idx].mean(0)
        medoid = idx[int(np.argmax(E[idx] @ c))]
        key = f"{fid}-S{s_i + 1}"
        for iid in sub["incident_id"]:
            strategy_of[iid] = key
        srcs = set(sub["resolution_notes_source"])
        text_prov = "original" if srcs == {"original"} else ("synthetic" if srcs == {"synthetic"} else "mixed")
        note = str(usable.at[medoid, "resolution_notes"])
        cc = Counter(sub["closure_code"]).most_common(3)
        strategies.append({
            "strategy_key": key, "pattern_id": fid,
            "label": action_summary(note), "representative_note": note,
            "representative_incident": str(usable.at[medoid, "incident_id"]),
            "n_incidents": int(len(sub)), "share_of_documented": round(len(sub) / len(usable), 3),
            "closure_codes": {k: int(v) for k, v in cc},
            "text_provenance": text_prov,
            "example_incident_ids": sub["incident_id"].head(8).tolist(),
            "centroid": (c / np.linalg.norm(c)).round(6).tolist(),
            **outcome_stats(sub),
        })
    for s in strategies:
        s["undocumented_resolutions_in_family"] = undocumented
    return strategies, strategy_of
