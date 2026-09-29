"""Clarification triggers, attempt tracking, guardrails, resolution ranking, evidence chain, metrics."""
from types import SimpleNamespace

import pytest

from backend.evaluation import metrics as M
from backend.rag.guardrails import safety_review
from backend.rag.resolution import expected_observation, rank_resolutions
from backend.rag.strategy import StrategyIndex, action_clauses, wilson
from backend.schemas.retrieval import RetrievalScores, RetrievedIncident, WhyRetrieved
from backend.troubleshooting.clarification import ClarificationPolicy, parse_answer

POLICY = ClarificationPolicy(confidence_threshold=0.45, family_margin=0.08, max_per_session=1)
FP_UNKNOWN = {"component": "Unknown", "impact_scope": "Unknown", "trigger": "Unknown", "environment": "Unknown",
              "symptom": "slow response"}


# ------------------------------------------------------------------ clarification
def test_asks_when_low_confidence_and_vague():
    q = POLICY.check(top_confidence=0.2, is_vague=True, families=[], fingerprint_values=FP_UNKNOWN, answered={},
                     asked_count=0)
    assert q and q.trigger == "low_confidence_vague" and q.field == "component"


def test_does_not_ask_when_confident_or_specific():
    assert POLICY.check(top_confidence=0.9, is_vague=True, families=[], fingerprint_values=FP_UNKNOWN, answered={},
                        asked_count=0) is None
    assert POLICY.check(top_confidence=0.2, is_vague=False, families=[], fingerprint_values=FP_UNKNOWN, answered={},
                        asked_count=0) is None


def test_never_asks_about_known_fields_or_more_than_once():
    known = {**FP_UNKNOWN, "component": "Database"}
    q = POLICY.check(top_confidence=0.2, is_vague=True, families=[], fingerprint_values=known,
                     answered={"impact_scope": "team"}, asked_count=0)
    assert q.field == "trigger"  # component known, scope answered → next missing field
    assert POLICY.check(top_confidence=0.2, is_vague=True, families=[], fingerprint_values=FP_UNKNOWN, answered={},
                        asked_count=1) is None  # at most one question per session


def test_asks_when_two_families_are_ambiguous_on_a_separating_field():
    fams = [{"family_id": "F1", "match_strength": 0.50, "signature": {"component": {"Database": 0.9}}},
            {"family_id": "F2", "match_strength": 0.46, "signature": {"component": {"Application": 0.8}}}]
    q = POLICY.check(top_confidence=0.9, is_vague=False, families=fams, fingerprint_values=FP_UNKNOWN, answered={},
                     asked_count=0)
    assert q and q.trigger == "ambiguous_families" and q.field == "component"
    fams[1]["match_strength"] = 0.2  # clear winner → no question
    assert POLICY.check(top_confidence=0.9, is_vague=False, families=fams, fingerprint_values=FP_UNKNOWN,
                        answered={}, asked_count=0) is None


def test_pre_escalation_question_and_answer_parsing():
    q = POLICY.check(top_confidence=None, is_vague=False, families=[], fingerprint_values=FP_UNKNOWN, answered={},
                     asked_count=0, about_to_escalate=True)
    assert q.trigger == "pre_escalation" and q.field == "trigger"
    assert parse_answer("trigger", "yes, after a deployment / release") == "deployment / release"
    assert parse_answer("impact_scope", "only me") == "single user"
    assert parse_answer("environment", "it's in prod") == "Production"
    assert parse_answer("trigger", "no") == "no recent change"
    assert parse_answer("component", "") is None


# ------------------------------------------------------------------ attempt tracking
def test_attempt_tracking_schema_and_rules(db):
    from backend.troubleshooting.attempts import AttemptTracker

    t = AttemptTracker()
    step = {"action": "Restart the service", "strategy_key": "F1-S1", "supporting_incidents": ["IM1", "IM2"],
            "expected_observation": "response times back to normal", "confidence": 0.8, "step": "note"}
    a = t.create(incident_id="NEW-T1", session_id="TS-T1", round_no=1, step=step)
    assert a["engineer_response"] == "PENDING" and a["attempt_id"].startswith("ATT-")
    r = t.respond(a["attempt_id"], "failed", notes="still slow")
    assert r["engineer_response"] == "FAILED" and r["excluded_from_next_suggestion"] is True
    assert r["timestamp"] and r["responded_at"]
    with pytest.raises(ValueError):
        t.respond(a["attempt_id"], "WORKED")  # already answered
    a2 = t.create(incident_id="NEW-T1", session_id="TS-T1", round_no=2, step=step)
    with pytest.raises(ValueError):
        t.respond(a2["attempt_id"], "MAYBE")  # only WORKED / FAILED / UNKNOWN
    assert [x["round"] for x in t.for_incident("NEW-T1")] == [1, 2]


# ------------------------------------------------------------------ guardrails / ranking
def _res(iid, note, conf, prov="synthetic", w=0.8):
    return RetrievedIncident(rank=1, incident_id=iid, title="t", description="d", resolution_notes=note, metadata={},
                             provenance={"resolution_notes": prov, "description": prov},
                             quality={"influence_weight": w, "tier": "high"},
                             scores=RetrievalScores(rrf_score=0.03, relevance_confidence=conf, rerank_logit=1.0,
                                                    confidence_basis="x"),
                             why_retrieved=WhyRetrieved(summary="s"))


def test_destructive_action_needs_two_sources():
    assert safety_review("Restored the table from backup", 1)["allowed"] is False
    ok = safety_review("Restored the table from backup", 2)
    assert ok["allowed"] and ok["requires_human_confirmation"]
    assert safety_review("Restarted the service", 1)["disruptive"]


def test_ranking_leads_with_one_top_pick_and_real_confidence():
    sidx = StrategyIndex([], {"A": "F1-S1", "B": "F1-S1", "C": "F1-S2"})
    results = [_res("A", "Restarted the application service; response times back to normal.", 0.9),
               _res("B", "Recycled the application service and verified memory usage dropped.", 0.8),
               _res("C", "Increased the heap size and tuned garbage collection settings.", 0.7),
               _res("D", "closed", 0.95)]
    r = rank_resolutions(results, sidx)
    assert r["top"]["strategy_key"] == "F1-S1" and len(r["alternatives"]) == 1
    comp = r["top"]["confidence_components"]
    assert r["top"]["confidence"] == pytest.approx(comp["max_relevance"] * comp["agreement"] * comp["provenance_factor"], abs=1e-3)
    assert "D" in r["skipped_low_quality_notes"]  # generic notes have no influence
    r2 = rank_resolutions(results, sidx, excluded_keys={"F1-S1"})
    assert r2["top"]["strategy_key"] == "F1-S2"  # failed strategy excluded → next-best
    unr = rank_resolutions(results, sidx, reranked=False)
    assert unr["top"]["confidence"] is None and "undetermined" in unr["top"]["confidence_basis"]


def test_family_prior_prefers_matched_family_strategies():
    sidx = StrategyIndex([], {"A": "F1-S1", "B": "F2-S1"})
    results = [_res("A", "Increased the heap size.", 0.6), _res("B", "Restarted the print spooler.", 0.7)]
    assert rank_resolutions(results, sidx)["top"]["strategy_key"] == "F2-S1"
    top = rank_resolutions(results, sidx, family={"family_id": "F1", "match_strength": 0.9})["top"]
    assert top["strategy_key"] == "F1-S1" and top["matched_family_strategy"]


def test_action_and_observation_extraction():
    note = "The memory leak was resolved by restarting the application service. As a result, response times are back to normal."
    assert action_clauses(note) == ["restarting the application service"]
    assert expected_observation(note).lower().startswith("response times are back to normal")
    lo, hi = wilson(5, 100)
    assert lo < 0.05 < hi


# ------------------------------------------------------------------ metrics
def test_ranking_metrics():
    rels = [0, 1, 1, 0]
    assert M.reciprocal_rank(rels) == 0.5
    assert M.precision_at_k(rels, 2) == 0.5
    assert M.hit_at_k(rels, 1) == 0.0
    assert M.ndcg_at_k([2, 0, 1], 3, [2, 1]) < 1.0 and M.ndcg_at_k([2, 1], 2, [2, 1]) == pytest.approx(1.0)
    assert M.context_precision([1, 0, 1], 3) == pytest.approx((1 + 2 / 3) / 2)


def test_clustering_metrics():
    pred, true = ["a", "a", "b", "b"], [1, 1, 2, 2]
    assert M.purity(pred, true) == 1.0
    pw = M.pairwise_prf(pred, true)
    assert pw["pairwise_precision"] == 1.0 and pw["pairwise_recall"] == 1.0
    assert M.pairwise_prf(["a", "a", "a", "a"], true)["pairwise_precision"] == pytest.approx(2 / 6, abs=1e-3)
