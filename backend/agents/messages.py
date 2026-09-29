"""Agent-to-agent (A2A) messages. Every hand-off between agents is an explicit, typed message that
is returned in API responses, so the orchestration is inspectable rather than implicit."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    intent: str  # e.g. PATTERN_CONTEXT, NOVEL_INCIDENT, STEP_PROPOSED, ESCALATE, PACKET_READY
    summary: str
    payload: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def as_dict(self) -> dict:
        return asdict(self)


def msg(sender: str, recipient: str, intent: str, summary: str, **payload) -> dict:
    return AgentMessage(sender, recipient, intent, summary, payload).as_dict()
