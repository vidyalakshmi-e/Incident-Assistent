"""Per-query evaluation: a relevant query grades Good, an unrelated or unseen one grades Poor."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.evaluation.query_eval import FAIR_MIN, GOOD_MIN, evaluate_query
from tests.conftest import DEMO


def _bundle(*, rel=0.95, known=0.9, novel=False, match=0.85, tokens=12, vague=False, concepts=("a",), hints=None):
    scores = SimpleNamespace(relevance_confidence=rel)
    result = SimpleNamespace(scores=scores)
    return SimpleNamespace(
        retrieval=SimpleNamespace(results=[result] if rel is not None else []),
        novelty={"is_novel": novel, "known_probability": known, "threshold": 0.49},
        families=[{"family_id": "F001", "match_strength": match}] if match is not None else [],
        qu=SimpleNamespace(technical_concepts=list(concepts), hints=hints or {}, token_count=tokens,
                           is_vague=vague, specificity=0.7),
    )


def test_clear_known_query_is_good():
    e = evaluate_query(_bundle(), {"confidence": 0.6})
    assert e["grade"] == "good" and e["score"] >= GOOD_MIN
    assert [c["key"] for c in e["components"]] == ["relevance", "known", "pattern", "fix"]


def test_unrelated_query_is_poor_with_a_reason():
    e = evaluate_query(_bundle(rel=0.02, known=0.0005, novel=True, match=0.01, concepts=(), tokens=6, vague=True), None)
    assert e["grade"] == "poor" and e["score"] < FAIR_MIN
    assert any("recognised" in n for n in e["notes"])


def test_novel_verdict_is_always_poor_even_with_a_high_score():
    e = evaluate_query(_bundle(rel=0.99, known=0.45, novel=True, match=0.99), {"confidence": 0.9})
    assert e["grade"] == "poor"  # the grade never contradicts the novel verdict shown beside it
    assert e["components"][3]["value"] == 0.0  # a novel incident never gets a fix forced onto it


def test_middle_score_is_fair():
    e = evaluate_query(_bundle(rel=0.74, known=0.74, match=0.62), {"confidence": 0.30})
    assert e["grade"] == "fair" and FAIR_MIN <= e["score"] < GOOD_MIN


def test_missing_signal_is_left_out_of_the_mean_not_counted_as_zero():
    e = evaluate_query(_bundle(known=None, rel=0.8, match=0.8), {"confidence": 0.8})
    known = next(c for c in e["components"] if c["key"] == "known")
    assert known["value"] is None and e["score"] == pytest.approx(0.8)


def test_very_short_query_is_told_to_add_detail():
    e = evaluate_query(_bundle(tokens=2, vague=True), {"confidence": 0.6})
    assert any("short" in n.lower() for n in e["notes"])


@pytest.mark.integration
def test_relevant_query_beats_unrelated_query_end_to_end(platform):
    good = platform.evaluate_query(DEMO)["evaluation"]
    bad = platform.evaluate_query("What is the best pizza recipe for a birthday party?")["evaluation"]
    assert good["grade"] == "good" and bad["grade"] == "poor"
    assert good["score"] > bad["score"] + 0.5


@pytest.mark.integration
def test_query_evaluation_endpoint_and_analyze_agree(client, platform):
    r = client.post("/evaluation/query", json={"text": DEMO})
    assert r.status_code == 200
    body = r.json()
    assert body["evaluation"]["grade"] == "good" and len(body["top_matches"]) == 3
    assert client.post("/evaluation/query", json={"text": ""}).status_code == 422
    assert platform.analyze(DEMO)["query_evaluation"]["score"] == body["evaluation"]["score"]
