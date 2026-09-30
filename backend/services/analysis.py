"""Core analysis pipeline shared by the API, the agents and the evaluation harness:

  query understanding → hybrid retrieval → enriched fingerprint → family match → novelty verdict
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from backend.intelligence.fingerprinting import Fingerprint
from backend.retrieval.query_understanding import QueryUnderstanding, understand
from backend.schemas.retrieval import RetrievalFilters, RetrievalResponse
from backend.services.timing import StageTimer


@dataclass
class AnalysisBundle:
    text: str
    qu: QueryUnderstanding
    retrieval: RetrievalResponse
    fingerprint: Fingerprint
    families: list[dict]
    novelty: dict
    q_emb: np.ndarray | None
    timer: StageTimer
    hints: dict[str, str] = field(default_factory=dict)
    # Every reranked result, before trimming to top_k. Only filled when a caller asks for a `pool`: the retriever
    # reranks 30 candidates whatever top_k is, so keeping them all costs nothing and lets the resolution ranker
    # see more distinct strategies without a second search.
    pool_results: list | None = None


def analyze_text(rt, text: str, filters: RetrievalFilters | None = None, hints: dict[str, str] | None = None,
                 exclude_ids: list[str] | None = None, top_k: int = 10, rerank: bool = True,
                 exclude_fn=None, pool: int | None = None) -> AnalysisBundle:
    timer = StageTimer()
    hints = dict(hints or {})
    with timer.stage("query_processing"):
        use_llm = rt.llm if rt.llm.available else None
        qu = understand(text, extra_context=hints, llm=use_llm,
                        vague_max_tokens=rt.s.clarification_vague_max_tokens)
    if exclude_ids:
        filters = (filters or RetrievalFilters()).model_copy()
        filters.exclude_incident_ids = list(set((filters.exclude_incident_ids or []) + list(exclude_ids)))
    retrieval = rt.retriever.search(text, filters=filters, top_k=max(top_k, pool or 0), rerank=rerank, qu=qu,
                                    exclude=exclude_fn, timer=timer)
    pool_results = None
    if pool and len(retrieval.results) > top_k:
        # the first top_k of a wider search are exactly what a top_k search returns; novelty and family matching
        # keep seeing that, unchanged
        pool_results = retrieval.results
        retrieval = retrieval.model_copy(update={"results": pool_results[:top_k]})
    with timer.stage("fingerprint"):
        fp = rt.fingerprinter.from_query(text, hints={**qu.hints, **hints})
    q_emb = None
    with timer.stage("pattern_match"):
        if retrieval.mode.semantic_available:
            q_emb = rt.embedder.embed([text])[0]
        families = rt.patterns.match(retrieval.results, q_emb)
    with timer.stage("novelty"):
        novelty = rt.novelty.assess(retrieval, families, fp)
    return AnalysisBundle(text, qu, retrieval, fp, families, novelty, q_emb, timer, hints, pool_results)
