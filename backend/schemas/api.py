"""API request / response models (Swagger / OpenAPI)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.retrieval import RetrievalFilters

EXAMPLE = ("The application is becoming slower and sometimes freezes when users try to open records. "
           "Restarting fixes it temporarily.")


class SearchRequest(BaseModel):
    query: str = Field(..., examples=[EXAMPLE])
    filters: RetrievalFilters | None = None
    top_k: int = Field(10, ge=1, le=50)
    rerank: bool = True


class EvaluateQueryRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=[EXAMPLE])


class IncidentFields(BaseModel):
    priority: str | None = Field(None, description="1-5 if known")
    impact: str | None = None
    urgency: str | None = None
    category: str | None = None
    ci_name: str | None = None


class AnalyzeRequest(BaseModel):
    text: str = Field(..., examples=[EXAMPLE])
    title: str | None = None
    fields: IncidentFields | None = None
    hints: dict[str, str] | None = Field(None, description="known fingerprint facts, e.g. {'environment': 'Production'}")
    filters: RetrievalFilters | None = None
    incident_id: str | None = Field(None, description="reuse an existing working incident")
    top_k: int = Field(10, ge=1, le=50)


class TriageRequest(AnalyzeRequest):
    pass


class ResolveRequest(BaseModel):
    text: str = Field(..., examples=[EXAMPLE])
    hints: dict[str, str] | None = None
    exclude_strategies: list[str] | None = Field(None, description="strategy keys that already failed")
    filters: RetrievalFilters | None = None


class TroubleshootRequest(BaseModel):
    action: Literal["start", "respond", "clarify", "escalate", "state"]
    text: str | None = Field(None, description="required for action=start", examples=[EXAMPLE])
    incident_id: str | None = None
    hints: dict[str, str] | None = None
    session_id: str | None = None
    attempt_id: str | None = None
    response: Literal["WORKED", "FAILED", "UNKNOWN"] | None = None
    notes: str | None = None
    answer: str | None = None
    declined: bool = False
    reason: str | None = None


class FeedbackRequest(BaseModel):
    incident_id: str
    session_id: str | None = None
    helpful: bool | None = Field(None, description="thumbs up (true) / down (false)")
    reasons: list[Literal["wrong incident", "wrong resolution", "incomplete", "outdated", "escalation required", "other"]] = []
    root_cause_correct: bool | None = None
    pattern_correct: bool | None = None
    troubleshooting_resolved: bool | None = None
    escalation_appropriate: bool | None = None
    comment: str | None = None
    supporting_incident_ids: list[str] | None = Field(
        None, description="historical incidents that backed the rated recommendation (for influence penalties)")
    process_kb_update: bool = Field(True, description="run the KB evolution loop immediately if the incident is resolved")


class EscalateRequest(BaseModel):
    session_id: str | None = None
    incident_id: str | None = None
    text: str | None = None
    reason: str = "requested by engineer"
    hints: dict[str, str] | None = None
    fields: IncidentFields | None = None


class SimulateRequest(BaseModel):
    preset: Literal["db-outage-burst", "vpn-storm", "memory-leak", "unrelated-noise"] | None = "db-outage-burst"
    texts: list[str] | None = Field(None, description="custom tickets (used instead of a preset)")
    interval_minutes: float = Field(4.0, description="spacing for custom tickets")
    reset: bool = False
    start_at: str | None = Field(None, description="ISO time of the first simulated ticket (default: now)")


class PostmortemRequest(BaseModel):
    incident_id: str
    feed_to_kb: bool = Field(True, description="run the KB evolution loop with the postmortem attached")


class ReviewRequest(BaseModel):
    approve: bool
    reviewer: str = "reviewer"


class EscalationResolveRequest(BaseModel):
    resolution_notes: str = Field(..., min_length=10, description="what the L2/L3 engineer did that fixed it")
    root_cause: str | None = Field(None, description="the root cause, if it was found")
    feed_to_kb: bool = Field(True, description="send the fix through the KB evolution quality check")


class EscalationHandoffRequest(BaseModel):
    note: str = Field(..., min_length=10, description="what the current tier tried and why the next tier is needed")


class GenericResponse(BaseModel):
    model_config = {"extra": "allow"}
    data: dict[str, Any] | None = None
