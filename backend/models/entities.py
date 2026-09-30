"""SQLAlchemy ORM models.

Structured / operational data lives here; vectors live in ChromaDB (keyed by incident_id) so the
two stores do not duplicate each other. The Evidence Chain is assembled at query time from these
tables and is not stored in a dedicated table.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.utcnow()


class Incident(Base):
    __tablename__ = "incidents"
    incident_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    origin: Mapped[str] = mapped_column(String(20), default="dataset", index=True)  # dataset | live | kb_evolution
    source: Mapped[str] = mapped_column(String(20), index=True)
    source_file: Mapped[str | None] = mapped_column(String(120))
    ticket_id: Mapped[str | None] = mapped_column(String(40))
    ticket_type: Mapped[str | None] = mapped_column(String(40))
    category: Mapped[str | None] = mapped_column(String(40), index=True)
    category_original: Mapped[str | None] = mapped_column(String(40))
    category_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    ci_name: Mapped[str | None] = mapped_column(String(40), index=True)
    ci_category: Mapped[str | None] = mapped_column(String(40))
    ci_subcategory: Mapped[str | None] = mapped_column(String(60))
    ci_group: Mapped[str | None] = mapped_column(String(30), index=True)
    impact: Mapped[str | None] = mapped_column(String(10))
    urgency: Mapped[str | None] = mapped_column(String(10))
    priority: Mapped[str | None] = mapped_column(String(10), index=True)
    severity: Mapped[str | None] = mapped_column(String(20))
    impact_scope: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str | None] = mapped_column(String(30))
    closure_code: Mapped[str | None] = mapped_column(String(60))
    closure_class: Mapped[str | None] = mapped_column(String(40))
    open_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    resolved_time: Mapped[datetime | None] = mapped_column(DateTime)
    reopen_time: Mapped[datetime | None] = mapped_column(DateTime)
    close_time: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_hours: Mapped[float | None] = mapped_column(Float)
    reopened: Mapped[bool | None] = mapped_column(Boolean)
    no_of_reassignments: Mapped[float | None] = mapped_column(Float)
    no_of_related_incidents: Mapped[float | None] = mapped_column(Float)
    related_change: Mapped[str | None] = mapped_column(String(40))
    kb_number: Mapped[str | None] = mapped_column(String(20), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    in_kb: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    text_generator: Mapped[str | None] = mapped_column(String(80))
    suggested_team: Mapped[str | None] = mapped_column(String(60))
    family_id: Mapped[str | None] = mapped_column(String(20), index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)  # field -> original|derived|synthetic|missing
    ground_truth: Mapped[dict] = mapped_column(JSON, default=dict)  # evaluation-only generator labels
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class IncidentFingerprint(Base):
    __tablename__ = "incident_fingerprints"
    incident_id: Mapped[str] = mapped_column(String(40), ForeignKey("incidents.incident_id"), primary_key=True)
    component: Mapped[str] = mapped_column(String(80), default="Unknown")
    service: Mapped[str] = mapped_column(String(120), default="Unknown")
    symptom: Mapped[str] = mapped_column(String(120), default="Unknown")
    failure_type: Mapped[str] = mapped_column(String(60), default="Unknown")
    trigger: Mapped[str] = mapped_column(String(120), default="Unknown")
    root_cause: Mapped[str] = mapped_column(String(160), default="Unknown")
    environment: Mapped[str] = mapped_column(String(30), default="Unknown")
    dependency: Mapped[str] = mapped_column(String(120), default="Unknown")
    business_impact: Mapped[str] = mapped_column(String(200), default="Unknown")
    impact_scope: Mapped[str] = mapped_column(String(60), default="Unknown")
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    extractor_version: Mapped[str] = mapped_column(String(30), default="rules-v1")


class IncidentPattern(Base):
    __tablename__ = "incident_patterns"
    pattern_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | emerging
    size: Mapped[int] = mapped_column(Integer, default=0)
    members_original_text: Mapped[int] = mapped_column(Integer, default=0)
    members_synthetic_text: Mapped[int] = mapped_column(Integer, default=0)
    signature: Mapped[dict] = mapped_column(JSON, default=dict)  # dominant fingerprint values + shares
    recurrence: Mapped[dict] = mapped_column(JSON, default=dict)
    causal_chain: Mapped[list] = mapped_column(JSON, default=list)
    centroid: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class IncidentRelationship(Base):
    __tablename__ = "incident_relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    src_id: Mapped[str] = mapped_column(String(40), index=True)
    dst_id: Mapped[str] = mapped_column(String(40), index=True)
    rel_type: Mapped[str] = mapped_column(String(40), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    tag: Mapped[str] = mapped_column(String(20))  # observed | derived | inferred
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class CausalChainLink(Base):
    __tablename__ = "causal_chain_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str | None] = mapped_column(String(40), index=True)
    pattern_id: Mapped[str | None] = mapped_column(String(20), index=True)
    position: Mapped[int] = mapped_column(Integer)
    stage: Mapped[str] = mapped_column(String(30))
    statement: Mapped[str] = mapped_column(Text)
    tag: Mapped[str] = mapped_column(String(20))  # observed | derived | inferred
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class ResolutionStrategy(Base):
    __tablename__ = "resolution_strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(String(20), index=True)
    strategy_key: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(Text)
    n_incidents: Mapped[int] = mapped_column(Integer)
    n_with_outcome: Mapped[int] = mapped_column(Integer, default=0)
    stats_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    reopen_rate: Mapped[float | None] = mapped_column(Float)
    reopen_ci_low: Mapped[float | None] = mapped_column(Float)
    reopen_ci_high: Mapped[float | None] = mapped_column(Float)
    median_resolution_hours: Mapped[float | None] = mapped_column(Float)
    mean_reassignments: Mapped[float | None] = mapped_column(Float)
    text_provenance: Mapped[str] = mapped_column(String(20))
    example_incident_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text)


class TroubleshootingSession(Base):
    __tablename__ = "troubleshooting_sessions"
    session_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active | awaiting_clarification | resolved | escalated
    round: Mapped[int] = mapped_column(Integer, default=0)
    query_text: Mapped[str] = mapped_column(Text)
    state: Mapped[dict] = mapped_column(JSON, default=dict)  # fingerprint, clarifications, family, excluded strategies
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ResolutionAttempt(Base):
    """Formal attempt-tracking record (Interactive Troubleshooting)."""
    __tablename__ = "resolution_attempts"
    attempt_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    round: Mapped[int] = mapped_column(Integer)
    step_description: Mapped[str] = mapped_column(Text)
    strategy_key: Mapped[str] = mapped_column(String(120))
    source_incident_ids: Mapped[list] = mapped_column(JSON, default=list)
    expected_observation: Mapped[str | None] = mapped_column(Text)
    engineer_response: Mapped[str] = mapped_column(String(10), default="PENDING")  # WORKED | FAILED | UNKNOWN | PENDING
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime)
    excluded_from_next_suggestion: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)


class IncidentFeedback(Base):
    __tablename__ = "incident_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40))
    helpful: Mapped[bool | None] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    root_cause_correct: Mapped[bool | None] = mapped_column(Boolean)
    pattern_correct: Mapped[bool | None] = mapped_column(Boolean)
    troubleshooting_resolved: Mapped[bool | None] = mapped_column(Boolean)
    escalation_appropriate: Mapped[bool | None] = mapped_column(Boolean)
    comment: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[int | None] = mapped_column(Integer)  # 1-5 stars: how far the incident got resolved (rating / 5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EscalationRecord(Base):
    __tablename__ = "escalations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40))
    tier: Mapped[str] = mapped_column(String(10))
    team: Mapped[str] = mapped_column(String(80))
    expertise: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str] = mapped_column(Text)
    packet: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EscalationResolution(Base):
    """What the next tier (L2/L3) did with an escalation. One row per resolved escalation; an
    escalation with no row here is still open."""
    __tablename__ = "escalation_resolutions"
    escalation_id: Mapped[int] = mapped_column(Integer, ForeignKey("escalations.id"), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    resolved_by: Mapped[str] = mapped_column(String(120))
    resolution_notes: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    kb_status: Mapped[str | None] = mapped_column(String(30))
    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EscalationHandoff(Base):
    """A tier passing an escalation on to the next one (L2 → L3). The old escalation stays as history;
    `to_escalation_id` is the new open escalation the higher tier works from."""
    __tablename__ = "escalation_handoffs"
    from_escalation_id: Mapped[int] = mapped_column(Integer, ForeignKey("escalations.id"), primary_key=True)
    to_escalation_id: Mapped[int] = mapped_column(Integer, ForeignKey("escalations.id"), index=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    from_tier: Mapped[str] = mapped_column(String(10))
    to_tier: Mapped[str] = mapped_column(String(10))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class KnowledgeQuality(Base):
    __tablename__ = "knowledge_quality"
    incident_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    score: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String(10))
    flags: Mapped[list] = mapped_column(JSON, default=list)
    components: Mapped[dict] = mapped_column(JSON, default=dict)
    dup_group: Mapped[str | None] = mapped_column(String(40))
    near_dup_group: Mapped[str | None] = mapped_column(String(40))
    canonical: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[str] = mapped_column(String(20), default="auto")  # auto | pending_review | approved | rejected
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class KBEvolutionEvent(Base):
    """Audit trail of the Knowledge Base Evolution loop."""
    __tablename__ = "kb_evolution_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    suite: Mapped[str] = mapped_column(String(40))
    metric: Mapped[str] = mapped_column(String(80))
    value: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Postmortem(Base):
    __tablename__ = "postmortems"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    fed_to_kb: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class LiveEvent(Base):
    __tablename__ = "live_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(String(40), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    text: Mapped[str] = mapped_column(Text)
    family_id: Mapped[str | None] = mapped_column(String(20))
    family_similarity: Mapped[float | None] = mapped_column(Float)
    fingerprint: Mapped[dict] = mapped_column(JSON, default=dict)
    alert_id: Mapped[str | None] = mapped_column(String(40))
    scenario_tag: Mapped[str | None] = mapped_column(String(60))  # set by the simulator (evaluation ground truth)


class CorrelationAlert(Base):
    __tablename__ = "correlation_alerts"
    alert_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    family_id: Mapped[str | None] = mapped_column(String(20))
    member_ids: Mapped[list] = mapped_column(JSON, default=list)
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    detection_latency_s: Mapped[float] = mapped_column(Float)
    shared_fields: Mapped[dict] = mapped_column(JSON, default=dict)
    mean_similarity: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="open")
