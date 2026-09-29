"""Novel Incident Detection (MAJOR DIFFERENTIATOR 2).

Decides whether a new incident resembles known patterns strongly enough to be matched, using
four real signals (no LLM involvement):

  max_relevance_logit — best cross-encoder logit among the retrieved incidents
  max_semantic        — best embedding cosine among the retrieved incidents
  centroid_similarity — best cosine between the incident and any family's symptom centroid
  fingerprint_support — share of the best family's members whose symptom equals the incident's
                        symptom (0.5 when the incident's symptom is Unknown)

They are combined by a logistic model into P(known). Model weights AND the decision threshold
are fitted on the *validation* split of a labelled query set (known paraphrased incidents vs.
seeded no-match probes) by `backend/evaluation/calibration.py`, and reported on the held-out
*test* split. If no calibration exists, the verdict is "undetermined" — the threshold is never
a hand-picked constant.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.config.settings import Settings, get_settings

FEATURES = ["max_relevance_logit", "max_semantic", "centroid_similarity", "fingerprint_support"]
NOVEL_TEXT = "NOVEL INCIDENT — no sufficiently similar historical incident found"
KNOWN_TEXT = "Known pattern — matched to historical incidents"


def novelty_features(retrieval, families: list[dict], fp) -> dict[str, float]:
    logits = [r.scores.rerank_logit for r in retrieval.results if r.scores.rerank_logit is not None]
    sems = [r.scores.semantic_similarity for r in retrieval.results if r.scores.semantic_similarity is not None]
    cents = [f["centroid_similarity"] for f in families if f.get("centroid_similarity") is not None]
    support = 0.5
    if families and fp is not None and fp.values.get("symptom", "Unknown") != "Unknown":
        support = float(families[0]["signature"].get("symptom", {}).get(fp.values["symptom"], 0.0))
    return {
        "max_relevance_logit": float(max(logits)) if logits else -12.0,
        "max_semantic": float(max(sems)) if sems else 0.0,
        "centroid_similarity": float(max(cents)) if cents else 0.0,
        "fingerprint_support": support,
    }


@dataclass
class NoveltyModel:
    weights: list[float]
    bias: float
    means: list[float]
    stds: list[float]
    threshold: float  # on P(known); below → novel

    def p_known(self, feats: dict[str, float]) -> float:
        x = np.array([(feats[f] - m) / s for f, m, s in zip(FEATURES, self.means, self.stds)])
        z = float(np.dot(self.weights, x) + self.bias)
        return 1.0 / (1.0 + math.exp(-z))

    def contributions(self, feats: dict[str, float]) -> dict[str, float]:
        return {f: round(w * (feats[f] - m) / s, 3) for f, w, m, s in zip(FEATURES, self.weights, self.means, self.stds)}


class NoveltyDetector:
    def __init__(self, settings: Settings | None = None, model: NoveltyModel | None = None):
        self.s = settings or get_settings()
        self.model = model or self._load()

    def _load(self) -> NoveltyModel | None:
        path = Path(self.s.evaluation_dir) / "calibration.json"
        try:
            d = json.loads(path.read_text(encoding="utf-8"))["novelty"]
            return NoveltyModel(d["weights"], d["bias"], d["means"], d["stds"], d["threshold"])
        except (FileNotFoundError, KeyError, ValueError):
            return None

    @property
    def calibrated(self) -> bool:
        return self.model is not None

    def assess(self, retrieval, families: list[dict], fp) -> dict:
        feats = novelty_features(retrieval, families, fp)
        if not retrieval.mode.reranked or not retrieval.mode.semantic_available:
            # the model was fitted with all four signals; a degraded retrieval cannot be judged fairly
            return {"verdict": "undetermined", "is_novel": None, "known_probability": None, "threshold": None,
                    "features": feats, "basis": "novelty model requires reranked hybrid retrieval; running in "
                                                 f"degraded mode ({', '.join(retrieval.mode.labels)})"}
        if self.model is None:
            return {"verdict": "undetermined", "is_novel": None, "known_probability": None, "threshold": None,
                    "features": feats, "basis": "novelty detector not calibrated — run scripts/calibrate.py"}
        p = self.model.p_known(feats)
        novel = p < self.model.threshold
        return {
            "verdict": NOVEL_TEXT if novel else KNOWN_TEXT, "is_novel": bool(novel),
            "known_probability": round(p, 4), "threshold": round(self.model.threshold, 4),
            "features": {k: round(v, 4) for k, v in feats.items()},
            "contributions": self.model.contributions(feats),
            "basis": "logistic model over 4 retrieval/fingerprint signals; weights and threshold fitted on the "
                     "validation split of the labelled novelty set (see Evaluation → Novelty)",
            "recommended_route": "fresh investigation (no historical playbook)" if novel else "historical resolution path",
        }
