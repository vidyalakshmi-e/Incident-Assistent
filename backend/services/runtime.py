"""Process-wide singletons (lazy). Every component is independently constructible for tests."""
from __future__ import annotations

import logging
import threading
from functools import cached_property

from backend.config.settings import Settings, get_settings

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        self.lock = threading.RLock()

    @cached_property
    def llm(self):
        from backend.rag.llm import LLMClient
        return LLMClient(self.s)

    @cached_property
    def embedder(self):
        from backend.retrieval.embeddings import EmbeddingService
        return EmbeddingService(self.s)

    @cached_property
    def reranker(self):
        from backend.retrieval.reranker import RerankerService
        return RerankerService(self.s)

    @cached_property
    def vectors(self):
        from backend.retrieval.vector_store import ChromaStore
        return ChromaStore(self.s)

    @cached_property
    def store(self):
        from backend.services.knowledge_store import KnowledgeStore
        from backend.knowledge.evolution import load_accepted_additions
        st = KnowledgeStore(self.s)
        load_accepted_additions(st)
        return st

    @cached_property
    def retriever(self):
        from backend.retrieval.hybrid import HybridRetriever
        return HybridRetriever(self.store, self.embedder, self.vectors, self.reranker, self.s, llm=self.llm)

    @cached_property
    def fingerprinter(self):
        from backend.intelligence.fingerprinting import Fingerprinter
        return Fingerprinter()

    @cached_property
    def patterns(self):
        from backend.intelligence.pattern_detection import PatternEngine
        return PatternEngine.load(self.s, self.store, self.embedder)

    @cached_property
    def novelty(self):
        from backend.intelligence.novelty import NoveltyDetector
        return NoveltyDetector(self.s)

    @cached_property
    def correlator(self):
        from backend.intelligence.correlation import LiveCorrelator
        from backend.services.analysis import analyze_text
        return LiveCorrelator(self.s, self.patterns, self.fingerprinter, self.embedder,
                              analyzer=lambda text: analyze_text(self, text, top_k=10))

    @cached_property
    def outcome_models(self):
        from backend.services.triage import OutcomeModels
        return OutcomeModels.load(self.s)


_runtime: Runtime | None = None
_lock = threading.Lock()


def get_runtime() -> Runtime:
    global _runtime
    with _lock:
        if _runtime is None:
            _runtime = Runtime()
        return _runtime


def set_runtime(rt: Runtime | None) -> None:
    """Used by tests to inject a runtime built on fixtures."""
    global _runtime
    with _lock:
        _runtime = rt
