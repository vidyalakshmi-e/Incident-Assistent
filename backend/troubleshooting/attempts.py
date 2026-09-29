"""Formal Resolution Attempt & Outcome Tracking.

    attempt_id | incident_id | step_description | expected_observation | engineer_response
    (WORKED / FAILED / UNKNOWN) | timestamp | excluded_from_next_suggestion

The full history feeds the escalation packet (so L2/L3 do not repeat failed work) and, after
resolution, the Knowledge Base Evolution loop.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select

from backend.database.session import session_scope
from backend.models.entities import ResolutionAttempt

VALID_RESPONSES = {"WORKED", "FAILED", "UNKNOWN"}


def _row(a: ResolutionAttempt) -> dict:
    return {
        "attempt_id": a.attempt_id, "incident_id": a.incident_id, "session_id": a.session_id, "round": a.round,
        "step_description": a.step_description, "strategy_key": a.strategy_key,
        "source_incident_ids": a.source_incident_ids, "expected_observation": a.expected_observation,
        "engineer_response": a.engineer_response, "timestamp": a.timestamp.isoformat() if a.timestamp else None,
        "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        "excluded_from_next_suggestion": a.excluded_from_next_suggestion, "confidence": a.confidence,
        "notes": a.notes,
    }


class AttemptTracker:
    def create(self, *, incident_id: str, session_id: str, round_no: int, step: dict) -> dict:
        with session_scope() as s:
            a = ResolutionAttempt(
                attempt_id=f"ATT-{uuid.uuid4().hex[:10]}", incident_id=incident_id, session_id=session_id,
                round=round_no, step_description=step["action"], strategy_key=step["strategy_key"],
                source_incident_ids=step["supporting_incidents"], expected_observation=step.get("expected_observation"),
                engineer_response="PENDING", timestamp=datetime.utcnow(), confidence=step.get("confidence"),
                notes=step.get("step"),
            )
            s.add(a)
            s.flush()
            return _row(a)

    def respond(self, attempt_id: str, response: str, notes: str | None = None) -> dict:
        response = response.upper()
        if response not in VALID_RESPONSES:
            raise ValueError(f"engineer_response must be one of {sorted(VALID_RESPONSES)}")
        with session_scope() as s:
            a = s.get(ResolutionAttempt, attempt_id)
            if a is None:
                raise KeyError(attempt_id)
            if a.engineer_response != "PENDING":
                raise ValueError(f"attempt {attempt_id} already answered ({a.engineer_response})")
            a.engineer_response = response
            a.responded_at = datetime.utcnow()
            a.excluded_from_next_suggestion = response == "FAILED"
            if notes:
                a.notes = f"{a.notes or ''}\n[engineer] {notes}".strip()
            return _row(a)

    def for_incident(self, incident_id: str) -> list[dict]:
        with session_scope() as s:
            rows = s.execute(select(ResolutionAttempt).where(ResolutionAttempt.incident_id == incident_id)
                             .order_by(ResolutionAttempt.timestamp)).scalars().all()
            return [_row(a) for a in rows]

    def for_session(self, session_id: str) -> list[dict]:
        with session_scope() as s:
            rows = s.execute(select(ResolutionAttempt).where(ResolutionAttempt.session_id == session_id)
                             .order_by(ResolutionAttempt.timestamp)).scalars().all()
            return [_row(a) for a in rows]
