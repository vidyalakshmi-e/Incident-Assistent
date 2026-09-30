"""L2 → L3 hand-off, persisted feedback penalties, historical incident lookup and the failing-LLM breaker.

These are unit tests: the runtime is a small stub, so no models or built artefacts are needed.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.database.session import session_scope
from backend.models.entities import EscalationRecord, EscalationResolution, KnowledgeQuality


def _platform(tiers=("L1", "L2", "L3")):
    from backend.services.platform import Platform

    return Platform(SimpleNamespace(s=SimpleNamespace(tiers=list(tiers))))


def _escalate(tier="L2", incident="NEW-TEST-1") -> int:
    with session_scope() as s:
        e = EscalationRecord(incident_id=incident, session_id="TS-test", tier=tier, team="Application Support",
                             expertise="Database", reason="troubleshooting ran out of steps",
                             packet={"packet_id": "ESC-orig", "tier": tier, "tier_reasons": ["priority 2"],
                                     "tier_order": ["L1", "L2", "L3"]})
        s.add(e)
        s.flush()
        return e.id


# ------------------------------------------------------------------ hand-off
def test_l2_hands_off_to_l3_and_keeps_history(db):
    p = _platform()
    first = _escalate("L2")
    out = p.hand_off_escalation(first, SimpleNamespace(note="  Checked pool limits and restarted twice; no change.  "))

    new, old = out["escalation"], out["previous"]
    assert old["status"] == "handed_off" and old["handed_off_to"]["tier"] == "L3"
    assert new["status"] == "open" and new["tier"] == "L3" and new["next_tier"] is None
    assert new["handed_off_from"]["tier"] == "L2" and new["handed_off_from"]["note"].startswith("Checked pool")
    assert new["packet"]["tier"] == "L3" and new["packet"]["packet_id"] != "ESC-orig"
    assert new["packet"]["tier_reasons"][0].startswith("handed off by L2")

    items = {e["escalation_id"]: e for e in p.escalations()["escalations"]}
    assert items[first]["status"] == "handed_off" and items[new["escalation_id"]]["status"] == "open"
    assert p.escalations()["open"] >= 1


def test_open_escalation_offers_the_next_tier_only_below_the_last(db):
    p = _platform()
    l2, l3 = _escalate("L2"), _escalate("L3")
    items = {e["escalation_id"]: e for e in p.escalations()["escalations"]}
    assert items[l2]["next_tier"] == "L3" and items[l3]["next_tier"] is None


def test_hand_off_rejects_last_tier_repeats_and_resolved(db):
    p = _platform()
    l3 = _escalate("L3")
    with pytest.raises(ValueError, match="last tier"):
        p.hand_off_escalation(l3, SimpleNamespace(note="nothing above L3 to hand this to"))

    l2 = _escalate("L2")
    p.hand_off_escalation(l2, SimpleNamespace(note="needs the vendor's access to the storage array"))
    with pytest.raises(ValueError, match="already handed off"):
        p.hand_off_escalation(l2, SimpleNamespace(note="trying to hand off a second time"))

    done = _escalate("L2")
    with session_scope() as s:
        s.add(EscalationResolution(escalation_id=done, incident_id="NEW-TEST-1", resolved_by="L2, Application Support",
                                   resolution_notes="Raised the pool limit."))
    with pytest.raises(ValueError, match="already resolved"):
        p.hand_off_escalation(done, SimpleNamespace(note="too late, it is fixed already"))
    with pytest.raises(KeyError):
        p.hand_off_escalation(999_999, SimpleNamespace(note="there is no such escalation"))


def test_escalation_list_orders_open_then_handed_off_then_resolved(db):
    p = _platform()
    a = _escalate("L2")
    p.hand_off_escalation(a, SimpleNamespace(note="handing this one up to L3 for a look"))
    b = _escalate("L2")
    with session_scope() as s:
        s.add(EscalationResolution(escalation_id=b, incident_id="NEW-TEST-1", resolved_by="L2, x", resolution_notes="fixed"))
    order = [e["status"] for e in p.escalations()["escalations"]]
    assert order == sorted(order, key={"open": 0, "handed_off": 1, "resolved": 2}.get)


def test_hand_off_api_validates_input(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.routes import router
    from backend.services.platform import set_platform

    app = FastAPI()  # just the router: importing backend.main loads torch, which must not happen this early on Windows
    app.include_router(router)
    set_platform(_platform())
    try:
        c = TestClient(app)
        assert c.post("/escalations/999999/hand-off", json={"note": "there is no such escalation"}).status_code == 404
        assert c.post("/escalations/1/hand-off", json={"note": "short"}).status_code == 422
    finally:
        set_platform(None)


# ------------------------------------------------------------------ feedback penalties
class _Store:
    def __init__(self):
        self.recs = {"HIST-1": {"incident_id": "HIST-1", "source": "A", "quality_score": 0.8, "quality_tier": "high",
                                "influence_weight": 0.72}}

    def get(self, iid):
        return self.recs.get(iid)


def test_feedback_penalty_reaches_a_historical_record_and_survives_a_restart(db):
    from backend.knowledge.evolution import FEEDBACK_PENALTY, KBEvolution, load_feedback_penalties

    store = _Store()
    evo = KBEvolution(SimpleNamespace(store=store, s=SimpleNamespace(kb_quality_threshold=0.55)))
    changes = evo.apply_feedback_penalty(["HIST-1", "HIST-1", "MISSING"], "wrong resolution")

    assert changes == [{"incident_id": "HIST-1", "influence_before": 0.72,
                        "influence_after": round(0.72 - FEEDBACK_PENALTY, 4)}]  # duplicates and unknown ids ignored
    assert store.recs["HIST-1"]["influence_weight"] == round(0.72 - FEEDBACK_PENALTY, 4)
    with session_scope() as s:
        kq = s.get(KnowledgeQuality, "HIST-1")
        assert kq.components["feedback_penalty"] == FEEDBACK_PENALTY and "feedback:wrong resolution" in kq.flags

    evo.apply_feedback_penalty(["HIST-1"], "outdated")  # penalties accumulate
    assert store.recs["HIST-1"]["influence_weight"] == round(0.72 - 2 * FEEDBACK_PENALTY, 4)

    restarted = _Store()  # a fresh process rebuilds the store from the parquet files
    assert load_feedback_penalties(restarted) == 1
    assert restarted.recs["HIST-1"]["influence_weight"] == round(0.72 - 2 * FEEDBACK_PENALTY, 4)
    assert restarted.recs["HIST-1"]["quality_score"] == round(0.8 - 2 * FEEDBACK_PENALTY, 4)


# ------------------------------------------------------------------ historical incident lookup
def test_historical_incident_resolves_from_the_knowledge_store(db):
    store = SimpleNamespace(
        get=lambda iid: {"title": "Batch job hangs", "description": "Nightly batch stops at step 4."} if iid == "IM1" else None,
        metadata_view=lambda iid: {"status": "Closed", "priority": "3", "open_time": "2024-01-02T03:04:05", "impact_scope": "team"})
    patterns = SimpleNamespace(fingerprint_of=lambda iid: SimpleNamespace(values={"component": "Batch / interface"}))
    p = Platform = _platform()
    p.rt = SimpleNamespace(s=p.rt.s, store=store, patterns=patterns)

    row, fp = p._historical_row("IM1")
    assert row["description"] == "Nightly batch stops at step 4." and row["origin"] == "historical"
    assert fp == {"component": "Batch / interface"}
    assert p._historical_row("nope") is None


# ------------------------------------------------------------------ failing LLM endpoint
def _client(**kw):
    from backend.config.settings import Settings
    from backend.rag.llm import LLMClient

    return LLMClient(Settings(llm_provider="openai", llm_api_key="k", **kw), read_cache=False)


def test_llm_with_a_key_that_keeps_failing_reports_retrieval_only(monkeypatch):
    from backend.rag import llm as llm_mod

    c = _client()
    monkeypatch.setattr(c, "_store", lambda *a: None)

    def boom(*a):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr(c, "_http_complete", boom)
    assert c.available
    for i in range(llm_mod.FAIL_LIMIT):
        assert c.complete(f"prompt {i}") is None
    assert not c.available and "keeps failing" in c.unavailable_reason
    assert c.status()["available"] is False and "RuntimeError" in c.status()["last_error"]

    c._tripped_at -= llm_mod.COOLDOWN_S + 1  # cooldown over: it tries again, and one success clears the streak
    monkeypatch.setattr(c, "_http_complete", lambda *a: "ok")
    assert c.available and c.complete("again") == "ok" and c.consecutive_failures == 0


def test_llm_without_a_key_stays_retrieval_only():
    from backend.config.settings import Settings
    from backend.rag.llm import LLMClient

    c = LLMClient(Settings(llm_provider="openai", llm_api_key=""))
    assert not c.available and c.unavailable_reason == "LLM_API_KEY is not set"


@pytest.mark.parametrize("value", ['# add your key here (blank → "Retrieval-only mode")', "sk-abc def", "  # note", "kéy"])
def test_llm_key_that_is_really_a_comment_is_not_used(value):
    """python-dotenv keeps `LLM_API_KEY=# add your key` as the value; it must not be sent as a bearer token."""
    from backend.config.settings import Settings
    from backend.rag.llm import LLMClient

    c = LLMClient(Settings(llm_provider="openai", llm_api_key=value))
    assert not c.available and "does not look like a key" in c.unavailable_reason


def test_llm_accepts_an_ordinary_key_and_a_gateway_base_url():
    from backend.config.settings import Settings
    from backend.rag.llm import LLMClient

    c = LLMClient(Settings(llm_provider="openai", llm_api_key="sk-proj_AbC-123.xyz", llm_base_url="https://gw.example.com/v1"))
    assert c.available and c.status()["base_url"] == "https://gw.example.com/v1"
