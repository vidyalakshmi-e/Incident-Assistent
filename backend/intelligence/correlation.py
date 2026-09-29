"""Live Incident Correlation (MAJOR DIFFERENTIATOR 3).

Detects when several new incidents arriving within a short time window describe the same thing and
flags a *possible single ongoing incident* instead of treating them as isolated tickets.

Two events are linked when they fall in the same window AND either
  * their texts are similar (embedding cosine ≥ similarity threshold), or
  * both are matched to the same known incident family by the retrieval evidence (the same family
    match the assistant shows; match strength >= FAMILY_MATCH_MIN and not flagged novel).
Connected components with ≥ `correlation_min_incidents` events raise an alert. Detection latency
is the time between the first member's arrival and the alert.

The similarity threshold is validated on simulated validation streams (Evaluation → Correlation).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np

from backend.config.settings import Settings, load_calibrated
from backend.database.session import session_scope
from backend.models.entities import CorrelationAlert, LiveEvent

FAMILY_MIN = 0.5  # centroid-similarity fallback (no analyzer)
FAMILY_MATCH_MIN = 0.3  # retrieval-based family match strength needed to link on family


@dataclass
class Event:
    incident_id: str
    text: str
    received_at: datetime
    emb: np.ndarray
    family_id: str | None
    family_sim: float
    fingerprint: dict
    scenario_tag: str | None = None
    alert_id: str | None = None


@dataclass
class Alert:
    alert_id: str
    members: list[str]
    first_seen: datetime
    detected_at: datetime
    family_id: str | None
    shared_fields: dict
    mean_similarity: float
    updates: int = 0
    history: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"alert_id": self.alert_id, "members": self.members, "size": len(self.members),
                "first_seen": self.first_seen.isoformat(), "detected_at": self.detected_at.isoformat(),
                "detection_latency_s": round((self.detected_at - self.first_seen).total_seconds(), 1),
                "family_id": self.family_id, "shared_fields": self.shared_fields,
                "mean_similarity": round(self.mean_similarity, 4),
                "message": f"Possible single ongoing incident: {len(self.members)} related tickets within "
                           f"{(self.detected_at - self.first_seen).total_seconds() / 60:.0f} min",
                "framing": "possible correlation — confirm before merging tickets"}


class LiveCorrelator:
    def __init__(self, s: Settings, patterns, fingerprinter, embedder, persist: bool = True,
                 similarity_threshold: float | None = None, analyzer=None):
        self.s = s
        self.patterns, self.fingerprinter, self.embedder = patterns, fingerprinter, embedder
        self.analyzer = analyzer  # text -> AnalysisBundle (retrieval-based family match)
        self.window = timedelta(minutes=s.correlation_window_minutes)
        self.min_incidents = s.correlation_min_incidents
        self.threshold = similarity_threshold if similarity_threshold is not None else \
            load_calibrated("correlation_similarity", s.correlation_similarity_threshold)
        self.persist = persist
        self.events: list[Event] = []
        self.alerts: dict[str, Alert] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.events.clear()
            self.alerts.clear()

    # ------------------------------------------------------------------ core
    def _linked(self, a: Event, b: Event) -> tuple[bool, float]:
        sim = float(a.emb @ b.emb)
        if sim >= self.threshold:
            return True, sim
        if a.family_id and a.family_id == b.family_id:
            return True, sim
        return False, sim

    def ingest(self, text: str, received_at: datetime | None = None, incident_id: str | None = None,
               scenario_tag: str | None = None) -> dict:
        received_at = received_at or datetime.utcnow()
        emb = self.embedder.embed([text])[0]
        fam, fsim, fam_basis = None, 0.0, "none"
        if self.analyzer is not None:
            b = self.analyzer(text)
            fp = b.fingerprint
            top = b.families[0] if b.families else None
            if top and (top.get("match_strength") or 0) >= FAMILY_MATCH_MIN and not b.novelty.get("is_novel"):
                fam, fsim, fam_basis = top["family_id"], float(top["match_strength"]), "retrieval evidence"
        else:
            fp = self.fingerprinter.from_query(text)
            sims = self.patterns.centroid_similarities(emb)
            if sims:
                f, sim = max(sims.items(), key=lambda kv: kv[1])
                if sim >= FAMILY_MIN:
                    fam, fsim, fam_basis = f, float(sim), "centroid similarity"
        ev = Event(incident_id or f"LIVE-{uuid.uuid4().hex[:8]}", text, received_at, emb, fam, fsim, fp.as_dict(),
                   scenario_tag)
        with self._lock:
            self.events.append(ev)
            recent = [e for e in self.events if received_at - self.window <= e.received_at <= received_at]
            component, links = self._component(ev, recent)
            alert = None
            if len(component) >= self.min_incidents:
                alert = self._upsert_alert(component, links, received_at)
        if self.persist:
            self._persist(ev, alert)
        return {"event": {"incident_id": ev.incident_id, "received_at": received_at.isoformat(), "text": text,
                          "family_id": ev.family_id, "family_match": round(fsim, 4), "family_basis": fam_basis,
                          "fingerprint": {k: v for k, v in fp.values.items() if v != "Unknown"}},
                "correlated_with": [e.incident_id for e in component if e is not ev],
                "alert": alert.as_dict() if alert else None}

    def _component(self, ev: Event, recent: list[Event]) -> tuple[list[Event], list[float]]:
        """Connected component of `ev` among recent events."""
        comp, frontier, links = [ev], [ev], []
        rest = [e for e in recent if e is not ev]
        while frontier:
            cur = frontier.pop()
            for e in list(rest):
                ok, sim = self._linked(cur, e)
                if ok:
                    comp.append(e)
                    frontier.append(e)
                    rest.remove(e)
                    links.append(sim)
        return comp, links

    def _upsert_alert(self, comp: list[Event], links: list[float], now: datetime) -> Alert:
        existing = {e.alert_id for e in comp if e.alert_id}
        fams = [e.family_id for e in comp if e.family_id]
        fam = max(set(fams), key=fams.count) if fams else None
        shared = {}
        for f in ("component", "symptom", "failure_type"):
            vals = [e.fingerprint["values"].get(f) for e in comp]
            if vals and all(v == vals[0] and v != "Unknown" for v in vals):
                shared[f] = vals[0]
        first = min(e.received_at for e in comp)
        if existing:
            aid = sorted(existing)[0]
            alert = self.alerts[aid]
            alert.members = sorted({*alert.members, *[e.incident_id for e in comp]})
            alert.updates += 1
            alert.family_id, alert.shared_fields = fam, shared
            alert.mean_similarity = float(np.mean(links)) if links else alert.mean_similarity
        else:
            aid = f"CORR-{uuid.uuid4().hex[:8]}"
            alert = Alert(aid, [e.incident_id for e in comp], first, now, fam, shared,
                          float(np.mean(links)) if links else 0.0)
            self.alerts[aid] = alert
        for e in comp:
            e.alert_id = aid
        return alert

    def _persist(self, ev: Event, alert: Alert | None) -> None:
        with session_scope() as s:
            s.add(LiveEvent(incident_id=ev.incident_id, received_at=ev.received_at, text=ev.text,
                            family_id=ev.family_id, family_similarity=ev.family_sim,
                            fingerprint=ev.fingerprint["values"], alert_id=ev.alert_id, scenario_tag=ev.scenario_tag))
            if alert:
                row = s.get(CorrelationAlert, alert.alert_id)
                if row is None:
                    s.add(CorrelationAlert(alert_id=alert.alert_id, family_id=alert.family_id, member_ids=alert.members,
                                           first_seen=alert.first_seen, detected_at=alert.detected_at,
                                           detection_latency_s=(alert.detected_at - alert.first_seen).total_seconds(),
                                           shared_fields=alert.shared_fields, mean_similarity=alert.mean_similarity))
                else:
                    row.member_ids, row.shared_fields = list(alert.members), dict(alert.shared_fields)
                    row.family_id, row.mean_similarity = alert.family_id, alert.mean_similarity

    def snapshot(self, limit: int = 50) -> dict:
        with self._lock:
            evs = sorted(self.events, key=lambda e: e.received_at, reverse=True)[:limit]
            return {"window_minutes": self.window.total_seconds() / 60, "min_incidents": self.min_incidents,
                    "similarity_threshold": self.threshold,
                    "events": [{"incident_id": e.incident_id, "received_at": e.received_at.isoformat(), "text": e.text,
                                "family_id": e.family_id, "alert_id": e.alert_id} for e in evs],
                    "alerts": [a.as_dict() for a in sorted(self.alerts.values(), key=lambda a: a.detected_at, reverse=True)]}


# ------------------------------------------------------------------ simulation presets
PRESETS: dict[str, list[tuple[int, str]]] = {
    "db-outage-burst": [
        (0, "Customer search in the CRM is timing out for everyone on the second floor"),
        (4, "Reports keep loading forever and then fail with a timeout, started this morning"),
        (9, "Database alert: average query time above 30 seconds, sessions waiting, CRM search very slow"),
    ],
    "vpn-storm": [
        (0, "My VPN keeps disconnecting every few minutes while working from home"),
        (3, "Remote colleagues cannot stay connected to the office network, the tunnel drops"),
        (6, "Tunnel monitor: site-to-site VPN flapping, many down events in the last hour"),
    ],
    "memory-leak": [
        (0, "The application is becoming slower and sometimes freezes when users try to open records"),
        (5, "Opening client records takes minutes and the screen freezes, a restart helps for a while"),
        (12, "Heap usage above 95% on the application node, response times degrading"),
    ],
    "unrelated-noise": [
        (0, "The printer on the third floor does not print, jobs stay in the queue"),
        (7, "My account gets locked every morning even though my password is correct"),
        (15, "SAP posting ends with a runtime error dump since the transport"),
    ],
}
