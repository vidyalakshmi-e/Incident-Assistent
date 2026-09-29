"""Integration tests: retrieval, fallbacks, evidence chain, troubleshooting workflow, KB evolution, API,
evaluation reproducibility. Require built artefacts (python scripts/build_all.py) and local models."""
from __future__ import annotations

import pytest

from tests.conftest import DEMO

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------ retrieval
def test_demo_query_retrieves_the_memory_leak_family(rt):
    resp = rt.retriever.search(DEMO, top_k=5)
    assert resp.mode.reranked and resp.mode.semantic_available and not resp.mode.labels
    fams = [rt.patterns.assign.get(r.incident_id) for r in resp.results]
    fam = rt.patterns.families[max(set(fams), key=fams.count)]
    assert "memory leak" in fam.name
    top = resp.results[0]
    assert 0 <= top.scores.relevance_confidence <= 1 and top.why_retrieved.summary
    assert "memory leak" in resp.query_understanding["technical_concepts"]  # vague → technical translation


def test_metadata_filters_and_exclusions_are_honoured(rt):
    from backend.schemas.retrieval import RetrievalFilters

    first = rt.retriever.search(DEMO, top_k=3).results[0].incident_id
    resp = rt.retriever.search(DEMO, filters=RetrievalFilters(priority=["3"], exclude_incident_ids=[first]), top_k=5)
    assert resp.results and all(r.metadata["priority"] == "3" for r in resp.results)
    assert first not in [r.incident_id for r in resp.results]


def test_exact_duplicates_are_collapsed(rt):
    resp = rt.retriever.search("Encoder crashed during media conversion", top_k=5)
    top = resp.results[0]
    assert top.duplicates_collapsed >= 10  # Source A has ~22 identical encoder tickets
    assert len({r.incident_id for r in resp.results}) == len(resp.results)


# ------------------------------------------------------------------ fallbacks (docs/FALLBACKS.md)
def test_llm_missing_gives_labelled_retrieval_only_mode(platform):
    out = platform.analyze(DEMO)
    assert "Retrieval-only mode — LLM unavailable" in out["mode_labels"]
    assert out["llm_synthesis"] is None and out["top_resolution"] is not None
    assert out["evidence_chain"]["llm_inference"]["label"] == "Retrieval-only mode — LLM unavailable"


def test_embedding_provider_misconfigured_falls_back_to_local():
    from backend.config.settings import Settings
    from backend.retrieval.embeddings import EmbeddingService

    svc = EmbeddingService(Settings(embedding_provider="openai", openai_api_key="", llm_api_key=""))
    assert svc.name.startswith("local:") and "openai unavailable" in svc.fallback_reason
    assert svc.embed(["x"]).shape == (1, 384)


def test_reranker_unavailable_results_are_labelled_unreranked(rt, monkeypatch):
    monkeypatch.setattr(rt.reranker, "reranker", None)
    resp = rt.retriever.search(DEMO, top_k=3)
    assert "unreranked" in resp.mode.labels and not resp.mode.reranked
    assert all(r.scores.relevance_confidence is None for r in resp.results)  # no invented confidence


def test_vector_db_unreachable_gives_keyword_only(rt, monkeypatch):
    from backend.retrieval.vector_store import VectorStoreUnavailable

    def boom(*a, **k):
        raise VectorStoreUnavailable("ChromaDB unreachable (test)")

    monkeypatch.setattr(rt.vectors, "query", boom)
    resp = rt.retriever.search(DEMO, top_k=3)
    assert "keyword-only (semantic search unavailable)" in resp.mode.labels
    assert resp.results and all(r.scores.semantic_rank is None for r in resp.results)


# ------------------------------------------------------------------ novelty + evidence chain
def test_novel_probe_is_flagged_and_evidence_is_not_fabricated(platform):
    out = platform.search("The quantum key distribution link between the data centers desynchronized", top_k=5)
    assert out["novelty"]["is_novel"] is True
    ch = out["evidence_chain"]
    assert ch["root_cause_evidence"]["status"] == "insufficient evidence"
    assert ch["matched_incident_family"]["status"] == "insufficient evidence"


def test_evidence_chain_is_complete_for_known_incident(platform):
    ch = platform.resolve(DEMO)["evidence_chain"]
    for key in ("query_understood", "extracted_fingerprint", "matched_incident_family", "retrieved_incidents",
                "root_cause_evidence", "resolution_evidence", "evidence_strength"):
        assert key in ch
    assert ch["completeness"]["complete_core"]
    for dim, v in ch["evidence_strength"].items():
        assert v["status"] in {"computed", "insufficient evidence"}
        assert v["value"] is None or 0 <= v["value"] <= 1


# ------------------------------------------------------------------ troubleshooting workflow
def test_failed_step_is_excluded_and_loop_escalates_with_history(platform):
    from backend.schemas.api import TroubleshootRequest as TR

    s = platform.troubleshoot(TR(action="start", text=DEMO))["session"]
    assert s["status"] == "active"
    seen, clar = [], 0
    for _ in range(8):
        if s["status"] == "awaiting_clarification":
            clar += 1
            s = platform.troubleshoot(TR(action="clarify", session_id=s["session_id"], declined=True))["session"]
            continue
        if s["status"] != "active":
            break
        seen.append(s["current_step"]["strategy_key"])
        s = platform.troubleshoot(TR(action="respond", session_id=s["session_id"],
                                     attempt_id=s["current_step"]["attempt_id"], response="FAILED"))["session"]
    assert len(seen) == len(set(seen)), "a failed strategy was suggested again"
    assert len(seen) <= platform.rt.s.troubleshooting_max_rounds + 1 and clar <= 1
    assert s["status"] == "escalated"
    packet = s["escalation"]
    assert len(packet["resolution_attempt_history"]) == len(seen)
    assert set(packet["failed_approaches_do_not_repeat"]) == set(seen)
    assert packet["tier"] in platform.rt.s.tiers and packet["clarification"]["attempted"] == (clar > 0)


def test_next_tier_resolves_an_escalation_and_it_feeds_the_kb(platform, no_vector_writes):
    from backend.schemas.api import EscalationResolveRequest as ER, TroubleshootRequest as TR
    from backend.services.incidents import incident_row

    text = "Nightly settlement batch SB-7 hangs at the reconciliation step and never finishes"
    s = platform.troubleshoot(TR(action="start", text=text))["session"]
    s = platform.troubleshoot(TR(action="escalate", session_id=s["session_id"], reason="test hand-off"))["session"]
    assert s["status"] == "escalated"
    listed = platform.escalations()
    esc = next(e for e in listed["escalations"] if e["session_id"] == s["session_id"])
    assert esc["status"] == "open" and esc["packet"]["tier"] == esc["tier"] and listed["open"] >= 1

    out = platform.resolve_escalation(esc["escalation_id"], ER(
        resolution_notes="Rebuilt the SB-7 reconciliation index and reran the batch; it finished in 12 minutes.",
        root_cause="stale reconciliation index"))
    assert out["escalation"]["status"] == "resolved"
    assert out["escalation"]["resolution"]["resolved_by"].startswith(esc["tier"])
    assert out["kb_update"]["status"] in ("added_to_kb", "pending_review")  # the normal quality gate decides
    assert incident_row(s["incident_id"])["status"] == "Resolved"
    view = platform.troubleshoot(TR(action="state", session_id=s["session_id"]))["session"]
    assert view["status"] == "escalated" and view["escalation_resolution"]["root_cause"] == "stale reconciliation index"
    with pytest.raises(ValueError):
        platform.resolve_escalation(esc["escalation_id"], ER(resolution_notes="a second attempt to close it"))


def test_escalation_api_validates_input(client):
    assert client.get("/escalations").status_code == 200
    assert client.post("/escalations/999999/resolve", json={"resolution_notes": "fixed the thing properly"}).status_code == 404
    assert client.post("/escalations/1/resolve", json={"resolution_notes": "ok"}).status_code == 422


def test_worked_step_resolves_and_kb_evolution_makes_it_retrievable(platform, no_vector_writes):
    from backend.schemas.api import FeedbackRequest, TroubleshootRequest as TR

    text = "Payroll export job ZX-99 aborted overnight because the upstream bank file arrived with a wrong header"
    s = platform.troubleshoot(TR(action="start", text=text))["session"]
    if s["status"] == "awaiting_clarification":
        s = platform.troubleshoot(TR(action="clarify", session_id=s["session_id"], declined=True))["session"]
    assert s["status"] == "active"
    s = platform.troubleshoot(TR(action="respond", session_id=s["session_id"], attempt_id=s["current_step"]["attempt_id"],
                                 response="WORKED", notes="Upstream team redelivered the ZX-99 file with the correct "
                                                          "header; reran the job and verified record counts."))["session"]
    assert s["status"] == "resolved"
    fb = platform.feedback(FeedbackRequest(incident_id=s["incident_id"], helpful=True, root_cause_correct=True,
                                           pattern_correct=True, troubleshooting_resolved=True))
    assert fb["kb_update"]["status"] == "added_to_kb"
    assert no_vector_writes, "embedding was not sent to the vector index"
    hits = platform.rt.retriever.search("ZX-99 payroll export wrong header", top_k=3)
    assert s["incident_id"] in [r.incident_id for r in hits.results]  # BM25 index rebuilt


def test_low_quality_resolution_goes_to_manual_review(platform, no_vector_writes):
    from backend.schemas.api import TroubleshootRequest as TR
    from backend.services.incidents import update_incident

    s = platform.troubleshoot(TR(action="start", text="The branch printer shows offline and nothing prints"))["session"]
    update_incident(s["incident_id"], status="Resolved", resolution_notes="ok")  # resolved outside the loop, poor note
    res = platform.evolution.process(s["incident_id"], force_review=True)
    assert res["status"] == "pending_review"
    assert platform.kb_review(s["incident_id"], approve=False, reviewer="test")["status"] == "rejected"


# ------------------------------------------------------------------ API
def test_api_endpoints(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.post("/incidents/search", json={"query": DEMO, "top_k": 3}).json()
    assert r["results"] and "evidence_chain" in r
    a = client.post("/incidents/analyze", json={"text": DEMO}).json()
    assert a["top_resolution"] and a["agent_messages"]
    iid = a["incident_id"]
    assert client.get(f"/incidents/{iid}").status_code == 200
    assert client.get(f"/incidents/{iid}/evidence-chain").json()["evidence_chain"]["subject"] == "analysis"
    assert client.get(f"/incidents/{iid}/attempts").json()["attempts"] == []
    t = client.post("/incidents/triage", json={"text": DEMO}).json()
    assert t["routing"]["tier"] in ("L1", "L2", "L3") and t["resolution_time_prediction"]
    assert client.post("/incidents/resolve", json={"text": DEMO}).json()["top_resolution"]
    p = client.get("/patterns").json()
    fid = p["families"][0]["family_id"]
    assert client.get(f"/patterns/{fid}").json()["family_id"] == fid
    assert client.get("/patterns/NOPE").status_code == 404
    sim = client.post("/incidents/simulate", json={"preset": "vpn-storm", "reset": True}).json()
    assert sim["alerts"], "VPN storm should raise a correlation alert"
    assert client.get("/incidents/correlations").json()["alerts"]
    e = client.post("/incidents/escalate", json={"text": DEMO, "reason": "test"}).json()
    assert e["packet"]["tier"] and e["packet"]["recommended_next_diagnostic_action"]
    assert client.post("/incidents/troubleshoot", json={"action": "respond"}).status_code in (400, 404)
    assert client.get("/incidents/IM-does-not-exist").status_code == 404
    assert client.get("/kb/quality").json()["records"] > 3000


# ------------------------------------------------------------------ evaluation reproducibility
@pytest.mark.slow
def test_evaluation_is_reproducible(rt):
    import pandas as pd

    from backend.evaluation.suite import eval_retrieval

    q = pd.read_json(rt.s.evaluation_dir / "eval_queries.jsonl", lines=True)
    q = q[q["label"] == "known"].head(8)
    a, b = eval_retrieval(rt, q), eval_retrieval(rt, q)
    assert a["configs"] == b["configs"]
