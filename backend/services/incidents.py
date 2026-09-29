"""Working ("live") incidents created by the assistant, and generic incident lookup."""
from __future__ import annotations

import uuid
from datetime import datetime

from backend.database.session import session_scope
from backend.models.entities import Incident


def new_incident_id() -> str:
    return f"NEW-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:4].upper()}"


def create_live_incident(text: str, title: str | None = None, fields: dict | None = None,
                         incident_id: str | None = None) -> str:
    """Persist an engineer-reported incident. Its text is real (engineer-reported) → 'original'."""
    iid = incident_id or new_incident_id()
    fields = fields or {}
    prov = {"description": "original", "title": "original" if title else "missing"}
    for k in ("priority", "impact", "urgency", "category"):
        prov[k] = "original" if fields.get(k) else "missing"
    with session_scope() as s:
        if s.get(Incident, iid) is None:
            s.add(Incident(
                incident_id=iid, origin="live", source="live", title=title or text[:80], description=text,
                status="Open", open_time=datetime.utcnow(), in_kb=False, provenance=prov,
                priority=fields.get("priority"), impact=fields.get("impact"), urgency=fields.get("urgency"),
                category=fields.get("category"), ci_name=fields.get("ci_name"), ground_truth={},
            ))
    return iid


def incident_row(iid: str) -> dict | None:
    with session_scope() as s:
        inc = s.get(Incident, iid)
        if inc is None:
            return None
        d = {c.name: getattr(inc, c.name) for c in Incident.__table__.columns}
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def update_incident(iid: str, **values) -> None:
    with session_scope() as s:
        inc = s.get(Incident, iid)
        if inc is None:
            raise KeyError(iid)
        for k, v in values.items():
            setattr(inc, k, v)
