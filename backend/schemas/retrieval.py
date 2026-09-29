"""Retrieval request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RetrievalFilters(BaseModel):
    priority: list[str] | None = Field(None, description="e.g. ['2','3']")
    impact: list[str] | None = None
    urgency: list[str] | None = None
    status: list[str] | None = Field(None, description="incident state, e.g. ['Closed']")
    category: list[str] | None = None
    team: list[str] | None = Field(None, description="derived support team")
    ci_group: list[str] | None = None
    source: list[str] | None = Field(None, description="A_text_rich | B_event_log | kb_evolution")
    text_provenance: list[str] | None = Field(None, description="original | synthetic")
    time_from: datetime | None = None
    time_to: datetime | None = None
    min_quality: float | None = None
    exclude_incident_ids: list[str] | None = None

    def is_empty(self) -> bool:
        return not any(v for v in self.model_dump().values())


class RetrievalScores(BaseModel):
    semantic_similarity: float | None = None
    semantic_rank: int | None = None
    bm25_score: float | None = None
    bm25_rank: int | None = None
    rrf_score: float
    rerank_logit: float | None = None
    relevance_confidence: float | None = Field(
        None, description="Calibrated P(relevant | cross-encoder logit). None when unreranked.")
    confidence_basis: str


class WhyRetrieved(BaseModel):
    summary: str
    matched_terms: list[str] = []
    matched_concepts: list[str] = []
    retrievers: list[str] = []
    filters_matched: dict[str, Any] = {}


class RetrievedIncident(BaseModel):
    rank: int
    incident_id: str
    title: str | None
    description: str | None
    resolution_notes: str | None
    metadata: dict[str, Any]
    provenance: dict[str, str]
    quality: dict[str, Any]
    scores: RetrievalScores
    why_retrieved: WhyRetrieved
    duplicates_collapsed: int = 0
    duplicate_ids: list[str] = []


class RetrievalMode(BaseModel):
    semantic_available: bool
    reranked: bool
    embedder: str
    reranker: str
    labels: list[str] = Field(default_factory=list, description="user-visible degraded-mode labels")
    notes: list[str] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    query_understanding: dict[str, Any]
    results: list[RetrievedIncident]
    mode: RetrievalMode
    candidates_considered: int
    timings_ms: dict[str, float]
