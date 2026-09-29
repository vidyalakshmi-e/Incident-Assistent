"""Cross-encoder reranking (FALLBACKS §3).

Chain: configured provider → local cross-encoder (ms-marco-MiniLM-L-6-v2) → no reranking.
When the last step is reached, results keep their hybrid-fusion order and are labelled
"unreranked" by the caller.
"""
from __future__ import annotations

import logging
import math
import os
from functools import lru_cache

import numpy as np

from backend.config.settings import Settings, get_settings

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

log = logging.getLogger(__name__)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


class LocalCrossEncoder:
    def __init__(self, model_id: str):
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_id)
        self.name = f"local:{model_id}"

    def score(self, query: str, docs: list[str]) -> np.ndarray:
        """Raw relevance logits."""
        if not docs:
            return np.zeros(0)
        return np.asarray(self.model.predict([(query, d) for d in docs], batch_size=64,
                                             show_progress_bar=False), dtype=np.float32)


class NvidiaReranker:
    def __init__(self, s: Settings):
        import httpx

        if not s.nvidia_api_key:
            raise ValueError("nvidia reranker: no API key configured")
        self.client = httpx.Client(timeout=20, headers={"Authorization": f"Bearer {s.nvidia_api_key}"})
        self.model = s.reranker_model_nvidia
        self.name = f"nvidia:{self.model}"
        self.url = f"https://ai.api.nvidia.com/v1/retrieval/{self.model}/reranking"

    def score(self, query: str, docs: list[str]) -> np.ndarray:
        r = self.client.post(self.url, json={"model": self.model, "query": {"text": query},
                                             "passages": [{"text": d} for d in docs]})
        r.raise_for_status()
        out = np.zeros(len(docs), dtype=np.float32)
        for item in r.json()["rankings"]:
            out[item["index"]] = item["logit"]
        return out


@lru_cache(maxsize=2)
def _local(model_id: str) -> LocalCrossEncoder:
    return LocalCrossEncoder(model_id)


class RerankerService:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.fallback_reason: str | None = None
        self.reranker = None
        requested = self.s.reranker_provider
        if requested == "none":
            self.fallback_reason = "reranking disabled by configuration"
            return
        try:
            self.reranker = NvidiaReranker(self.s) if requested == "nvidia" else _local(self.s.reranker_model_local)
        except Exception as exc:  # noqa: BLE001
            self.fallback_reason = f"{requested} reranker unavailable ({exc})"
            log.warning("Reranker fallback: %s", self.fallback_reason)
            self._fallback_local()
        log.info("Reranker in use: %s", self.name)

    def _fallback_local(self) -> None:
        try:
            self.reranker = _local(self.s.reranker_model_local)
        except Exception as exc:  # noqa: BLE001
            self.reranker = None
            self.fallback_reason = (self.fallback_reason or "") + f"; local cross-encoder failed ({exc}) — results unreranked"
            log.error("Reranker unavailable: results will be unreranked (%s)", exc)

    @property
    def name(self) -> str:
        return self.reranker.name if self.reranker else "none (unreranked)"

    @property
    def available(self) -> bool:
        return self.reranker is not None

    def score(self, query: str, docs: list[str]) -> np.ndarray | None:
        """Return logits, or None when no reranker could be used (caller labels 'unreranked')."""
        if not self.reranker:
            return None
        try:
            return self.reranker.score(query, docs)
        except Exception as exc:  # noqa: BLE001
            self.fallback_reason = f"{self.reranker.name} failed at request time ({exc})"
            log.warning("Reranker fallback: %s", self.fallback_reason)
            if not self.reranker.name.startswith("local:"):
                self._fallback_local()
                return self.score(query, docs)
            return None


def logit_to_prob(logit: float, a: float = 1.0, b: float = 0.0) -> float:
    """Platt-scaled relevance probability. a/b come from calibration on labelled validation
    queries (backend/evaluation/calibration.py); the defaults are the plain sigmoid."""
    return 1.0 / (1.0 + math.exp(-(a * logit + b)))
