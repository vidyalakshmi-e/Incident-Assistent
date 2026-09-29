"""Embedding providers (FALLBACKS §2).

Default: local sentence-transformers all-MiniLM-L6-v2. External providers (OpenAI, NVIDIA NIM)
are used only when configured *and* a key is present; any failure falls back to the local model
and the provider actually used is logged and reported.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Protocol

import numpy as np

from backend.config.settings import Settings, get_settings

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class LocalSTEmbedder:
    def __init__(self, model_id: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_id)
        self.name = f"local:{model_id}"

    def embed(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, batch_size=64, normalize_embeddings=True,
                                 show_progress_bar=False, convert_to_numpy=True).astype(np.float32)


class _HTTPEmbedder:
    """OpenAI-compatible /embeddings endpoint (OpenAI, NVIDIA NIM)."""

    def __init__(self, base_url: str, api_key: str, model: str, name: str, extra: dict | None = None):
        import httpx

        if not api_key:
            raise ValueError(f"{name}: no API key configured")
        self.client = httpx.Client(base_url=base_url, timeout=20,
                                   headers={"Authorization": f"Bearer {api_key}"})
        self.model, self.extra, self.name = model, extra or {}, f"{name}:{model}"

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 96):
            r = self.client.post("/embeddings", json={"model": self.model, "input": texts[i:i + 96], **self.extra})
            r.raise_for_status()
            out += [d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"])]
        v = np.asarray(out, dtype=np.float32)
        return v / np.linalg.norm(v, axis=1, keepdims=True)


@lru_cache(maxsize=4)
def _local(model_id: str) -> LocalSTEmbedder:
    return LocalSTEmbedder(model_id)


def build_embedder(provider: str, s: Settings) -> Embedder:
    if provider == "openai":
        return _HTTPEmbedder("https://api.openai.com/v1", s.openai_api_key or s.llm_api_key,
                             s.embedding_model_openai, "openai")
    if provider == "nvidia":
        return _HTTPEmbedder(s.nvidia_base_url, s.nvidia_api_key, s.embedding_model_nvidia, "nvidia",
                             extra={"input_type": "query", "truncate": "END"})
    return _local(s.embedding_model_local)


class EmbeddingService:
    """Resolves the configured provider once, falling back to local on any failure."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.requested = self.s.embedding_provider
        self.fallback_reason: str | None = None
        try:
            self.embedder = build_embedder(self.requested, self.s)
            if self.requested != "local":
                self.embedder.embed(["connectivity check"])  # fail fast on bad key / endpoint
        except Exception as exc:  # noqa: BLE001 — any provider failure → local fallback
            self.fallback_reason = f"{self.requested} unavailable ({type(exc).__name__}: {exc}); using local model"
            log.warning("Embedding fallback: %s", self.fallback_reason)
            self.embedder = _local(self.s.embedding_model_local)
        log.info("Embedding provider in use: %s", self.embedder.name)

    @property
    def name(self) -> str:
        return self.embedder.name

    def embed(self, texts: list[str]) -> np.ndarray:
        try:
            return self.embedder.embed(texts)
        except Exception as exc:  # noqa: BLE001
            if self.embedder.name.startswith("local:"):
                raise
            self.fallback_reason = f"{self.embedder.name} failed at request time ({exc}); using local model"
            log.warning("Embedding fallback: %s", self.fallback_reason)
            self.embedder = _local(self.s.embedding_model_local)
            return self.embedder.embed(texts)
