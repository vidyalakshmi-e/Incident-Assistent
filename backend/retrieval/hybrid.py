"""Hybrid retrieval: semantic (ChromaDB) + BM25 → Reciprocal Rank Fusion → cross-encoder rerank.

Why RRF: the two retrievers produce scores on incomparable scales (cosine vs. BM25). RRF fuses
*ranks*, needs no score normalisation, and is robust when one retriever is missing (which is
exactly the ChromaDB-unavailable fallback). k=60 is the value from Cormack et al. (2009).

Fallbacks handled here (docs/FALLBACKS.md):
  §2 embedding provider → handled inside EmbeddingService (local model)
  §3 reranker unavailable → fusion order, labelled "unreranked"
  §6 ChromaDB unreachable → BM25-only, labelled "keyword-only (semantic search unavailable)"
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from backend.config.settings import Settings, calibration_available, get_settings, load_calibrated
from backend.retrieval.bm25_index import BM25Index, analyze
from backend.retrieval.embeddings import EmbeddingService
from backend.retrieval.query_understanding import QueryUnderstanding, understand
from backend.retrieval.reranker import RerankerService, logit_to_prob
from backend.retrieval.vector_store import ChromaStore, VectorStoreUnavailable
from backend.schemas.retrieval import (
    RetrievalFilters, RetrievalMode, RetrievalResponse, RetrievalScores, RetrievedIncident, WhyRetrieved,
)
from backend.services.knowledge_store import KnowledgeStore
from backend.services.timing import StageTimer

log = logging.getLogger(__name__)

KEYWORD_ONLY_LABEL = "keyword-only (semantic search unavailable)"
UNRERANKED_LABEL = "unreranked"


def rrf(rankings: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


class HybridRetriever:
    def __init__(self, store: KnowledgeStore, embedder: EmbeddingService, vectors: ChromaStore,
                 reranker: RerankerService, settings: Settings | None = None, llm=None):
        self.s = settings or get_settings()
        self.store, self.embedder, self.vectors, self.reranker, self.llm = store, embedder, vectors, reranker, llm
        self.bm25 = BM25Index(store.chunks["chunk_id"].tolist(), store.chunks["text"].tolist())
        self.vector_available = True
        self._last_vector_check = 0.0
        self._check_vector_embedder()

    def _check_vector_embedder(self) -> None:
        """The query must be embedded in the same space as the index."""
        import time

        self._last_vector_check = time.time()
        self.vector_available = True
        try:
            idx_name = self.vectors.embedder_name()
            if idx_name and idx_name != self.embedder.name:
                log.warning("Index built with %s but query embedder is %s — semantic search disabled",
                            idx_name, self.embedder.name)
                self.vector_available = False
                self._embedder_mismatch = f"index embedder {idx_name} != query embedder {self.embedder.name}"
            else:
                self._embedder_mismatch = None
        except VectorStoreUnavailable as exc:
            self.vector_available = False
            self._embedder_mismatch = None
            log.warning("Vector store unavailable at start-up: %s", exc)

    def rebuild_bm25(self) -> None:
        self.bm25 = BM25Index(self.store.chunks["chunk_id"].tolist(), self.store.chunks["text"].tolist())

    # ------------------------------------------------------------------ search
    def search(self, query: str, filters: RetrievalFilters | None = None, top_k: int | None = None,
               rerank: bool = True, qu: QueryUnderstanding | None = None,
               exclude: Callable[[dict], bool] | None = None, collapse_duplicates: bool = True,
               timer: StageTimer | None = None) -> RetrievalResponse:
        top_k = top_k or self.s.default_top_k
        timer = timer or StageTimer()
        mode_labels, notes = [], []
        with timer.stage("query_processing"):
            if qu is None:
                use_llm = self.llm if (self.llm is not None and self.llm.available) else None
                qu = understand(query, llm=use_llm, vague_max_tokens=self.s.clarification_vague_max_tokens)
        n = self.s.retrieval_candidates

        # ---- semantic
        sem: list[tuple[str, float, dict]] = []
        if not self.vector_available and not self._embedder_mismatch:
            import time

            if time.time() - self._last_vector_check > 30:  # vector DB came back? (e.g. Chroma server started after the API)
                self._check_vector_embedder()
        semantic_ok = self.vector_available
        if semantic_ok:
            try:
                with timer.stage("embedding"):
                    qv = self.embedder.embed([qu.expanded_query])[0]
                with timer.stage("vector_search"):
                    sem = self.vectors.query(qv, n=n, where=self.store.chroma_where(filters, collapse_duplicates))
                    # vectors whose record is not in this store (e.g. pending review / other DB) are ignored
                    sem = [x for x in sem if x[0] in self.store.chunk_pos]
            except VectorStoreUnavailable as exc:
                semantic_ok = False
                notes.append(str(exc))
        if not semantic_ok:
            mode_labels.append(KEYWORD_ONLY_LABEL)
            if self._embedder_mismatch:
                notes.append(self._embedder_mismatch)
        if self.embedder.fallback_reason:
            notes.append(f"embedding fallback: {self.embedder.fallback_reason}")

        # ---- BM25
        with timer.stage("bm25"):
            # exact duplicates are collapsed *before* ranking (canonical members only) so 20 copies of
            # one ticket cannot crowd out distinct evidence; group sizes are reported per result
            mask = self.store.filter_mask(filters, canonical_only=collapse_duplicates)
            bm = self.bm25.search(qu.expanded_query, n=n, allowed=mask)

        # ---- fusion
        with timer.stage("hybrid_fusion"):
            sem_rank = {cid: (i + 1, sim) for i, (cid, sim, _) in enumerate(sem)}
            bm_rank = {cid: (i + 1, sc, terms) for i, (cid, sc, terms) in enumerate(bm)}
            fused = rrf([[c for c, _, _ in sem], [c for c, _, _ in bm]], k=self.s.rrf_k)
            order = sorted(fused, key=lambda c: -fused[c])
            if exclude is not None:
                order = [c for c in order if not exclude(self.store.get(self.store.chunk_incident[self.store.chunk_pos[c]]))]
            candidates = order[: max(self.s.rerank_top_n, top_k)]

        # ---- rerank
        logits = None
        if rerank and candidates:
            with timer.stage("reranking"):
                ce_query = qu.original if not qu.technical_concepts else f"{qu.original} ({', '.join(qu.technical_concepts[:6])})"
                logits = self.reranker.score(ce_query, [self.store.chunk_text(c) for c in candidates])
            if logits is None:
                mode_labels.append(UNRERANKED_LABEL)
                if self.reranker.fallback_reason:
                    notes.append(self.reranker.fallback_reason)
        elif not rerank:
            mode_labels.append(UNRERANKED_LABEL)
            notes.append("reranking skipped by request")
        if logits is not None:
            ranked = [c for _, c in sorted(zip(-logits, candidates), key=lambda t: t[0])]
            logit_of = dict(zip(candidates, logits.tolist()))
        else:
            ranked, logit_of = candidates, {}

        # ---- collapse duplicates + build results
        a = load_calibrated("ce_platt_a", 1.0)
        b = load_calibrated("ce_platt_b", 0.0)
        self._calibrated = calibration_available("ce_platt_a")
        results: list[RetrievedIncident] = []
        seen: set[str] = set()
        q_terms = set(analyze(qu.expanded_query))
        for cid in ranked:
            iid = self.store.chunk_incident[self.store.chunk_pos[cid]]
            if iid in seen:  # several chunks of one long incident
                continue
            seen.add(iid)
            rec = self.store.get(iid)
            item = self._build_item(len(results) + 1, cid, iid, rec, sem_rank, bm_rank, fused, logit_of, qu,
                                    q_terms, filters, a, b)
            if collapse_duplicates:
                dups = self.store.duplicates_of(iid)
                item.duplicates_collapsed, item.duplicate_ids = len(dups), dups[:25]
            results.append(item)
            if len(results) >= top_k:
                break

        mode = RetrievalMode(semantic_available=semantic_ok, reranked=logits is not None,
                             embedder=self.embedder.name, reranker=self.reranker.name,
                             labels=mode_labels, notes=notes)
        return RetrievalResponse(query_understanding=qu.as_dict(), results=results, mode=mode,
                                 candidates_considered=len(fused), timings_ms=dict(timer.timings_ms))

    def _build_item(self, rank, cid, iid, rec, sem_rank, bm_rank, fused, logit_of, qu, q_terms, filters, a, b):
        s_r = sem_rank.get(cid)
        b_r = bm_rank.get(cid)
        logit = logit_of.get(cid)
        conf = round(logit_to_prob(logit, a, b), 4) if logit is not None else None
        retrievers = (["semantic"] if s_r else []) + (["bm25"] if b_r else [])
        matched_terms = b_r[2] if b_r else sorted(q_terms & set(analyze(self.store.chunk_text(cid))))
        doc_lower = self.store.chunk_text(cid).lower()
        matched_concepts = [c for c in qu.technical_concepts if all(w in doc_lower for w in c.lower().split())]
        parts = []
        if s_r:
            parts.append(f"semantic rank {s_r[0]} (cosine {s_r[1]:.2f})")
        if b_r:
            parts.append(f"BM25 rank {b_r[0]} on terms {', '.join(b_r[2][:6])}")
        if logit is not None:
            parts.append(f"cross-encoder relevance {conf:.2f}")
        filt = {} if filters is None else {k: v for k, v in filters.model_dump().items() if v and k != "exclude_incident_ids"}
        return RetrievedIncident(
            rank=rank, incident_id=iid, title=rec.get("title"), description=rec.get("description"),
            resolution_notes=rec.get("resolution_notes"),
            metadata=self.store.metadata_view(iid), provenance=self.store.provenance_view(iid),
            quality={"score": float(rec.get("quality_score", 0)), "tier": rec.get("quality_tier"),
                     "flags": list(rec.get("quality_flags", [])),
                     "influence_weight": float(rec.get("influence_weight", 0))},
            scores=RetrievalScores(
                semantic_similarity=round(s_r[1], 4) if s_r else None, semantic_rank=s_r[0] if s_r else None,
                bm25_score=round(b_r[1], 3) if b_r else None, bm25_rank=b_r[0] if b_r else None,
                rrf_score=round(fused.get(cid, 0.0), 5), rerank_logit=round(logit, 3) if logit is not None else None,
                relevance_confidence=conf,
                confidence_basis=(("Platt-calibrated cross-encoder probability" if self._calibrated
                                   else "sigmoid of cross-encoder logit (not yet calibrated)") if conf is not None
                                  else "unreranked: reciprocal-rank-fusion score only (no confidence shown)")),
            why_retrieved=WhyRetrieved(summary="; ".join(parts), matched_terms=list(matched_terms)[:12],
                                       matched_concepts=matched_concepts, retrievers=retrievers,
                                       filters_matched=filt),
        )


def normalized_rrf(score: float, n_retrievers: int = 2, k: int = 60) -> float:
    """RRF score divided by its maximum possible value (rank 1 in every retriever)."""
    return float(np.clip(score / (n_retrievers / (k + 1)), 0, 1))
