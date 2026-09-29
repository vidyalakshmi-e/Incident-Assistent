"""Conditioned synthetic generation + Knowledge Quality Manager."""
import numpy as np
import pandas as pd

from backend.data_pipeline.scenarios import SCENARIO_BY_ID
from backend.data_pipeline.synthetic import LOW_QUALITY_NOTES, TemplateVerbalizer, plan_synthetic_rows
from backend.knowledge.quality import (
    closure_note_conflict, exact_duplicate_groups, near_duplicate_groups, resolution_detail, score_record,
)


def eligible_rows(n=400, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    groups = ["app_server", "app_web", "enduser_hw", "database", "network", "storage"]
    subcats = {"app_server": "Server Based Application", "app_web": "Web Based Application", "enduser_hw": "Laptop",
               "database": "Database", "network": "Switch", "storage": "SAN"}
    codes = ["Software", "Hardware", "Other", "Unknown", "User error", "Data", "No error - works as designed"]
    g = rng.choice(groups, n)
    return pd.DataFrame({
        "incident_id": [f"IM{i:05d}" for i in range(n)], "ci_group": g, "ci_subcategory": [subcats[x] for x in g],
        "ci_name": [f"CI{i:04d}" for i in range(n)], "closure_code": rng.choice(codes, n),
        "impact": rng.choice(["3", "4", "5"], n), "urgency": rng.choice(["3", "4", "5"], n),
        "no_of_reassignments": rng.integers(0, 6, n), "related_change": [None] * n,
    })


def test_generation_is_conditioned_on_real_fields():
    df = eligible_rows()
    briefs = plan_synthetic_rows(df, seed=1, target=200)
    rows = df.set_index("incident_id")
    assert briefs, "no rows planned"
    for b in briefs:
        sc = SCENARIO_BY_ID[b.scenario_id]
        r = rows.loc[b.incident_id]
        assert r["ci_group"] in sc.ci_groups, "scenario incompatible with the real CI"
        assert r["closure_code"] in sc.closure_codes, "scenario incompatible with the real closure code"
        assert b.ci == r["ci_name"]
    assert len({b.incident_id for b in briefs}) == len(briefs)  # each real row used at most once


def test_generation_seeds_low_quality_and_contradictions_and_views():
    briefs = plan_synthetic_rows(eligible_rows(800, 3), seed=2, target=400)
    assert any(b.note_quality == "low" for b in briefs)
    assert any(b.seeded_defect == "contradiction" for b in briefs)
    assert len({b.view for b in briefs}) >= 2  # differently-worded symptom views
    tv = TemplateVerbalizer()
    low = next(b for b in briefs if b.note_quality == "low")
    assert tv.render(low)["resolution_notes"] in LOW_QUALITY_NOTES


def test_generic_and_empty_notes_are_flagged():
    assert resolution_detail("closed")[1] == ["generic_resolution"]
    assert resolution_detail("")[1] == ["empty_resolution"]
    detailed, flags = resolution_detail("Heap was exhausted due to a leak. Restarted the service and verified "
                                        "response times are back to normal.")
    assert detailed > 0.8 and not flags


def test_duplicates_and_near_duplicates():
    kb = pd.DataFrame({"incident_id": ["a", "b", "c"], "title": ["T", "T", "X"], "description": ["d", "d", "y"],
                       "resolution_notes": ["r", "r", "z"]})
    assert exact_duplicate_groups(kb).tolist() == ["a", "a", "c"]
    emb = np.array([[1, 0], [0.999, 0.0447], [0, 1]], dtype=np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    assert near_duplicate_groups(["a", "b", "c"], emb, 0.95) == ["a", "a", "c"]


def test_contradiction_between_closure_code_and_note():
    assert closure_note_conflict("hardware_fix", "Installed the vendor patch and restarted the service")
    assert not closure_note_conflict("hardware_fix", "Replaced the defective card reader module")
    assert closure_note_conflict("no_fault_found", "Replaced the disk")


def test_quality_score_orders_records_sensibly():
    good = pd.Series({"resolution_notes": "Pool was exhausted. Increased the pool size and verified no timeouts.",
                      "reopened": False, "reopened_source": "derived", "no_of_reassignments": 0,
                      **{f"{f}_source": "original" for f in ("impact", "urgency", "priority", "closure_code", "open_time", "resolved_time")}})
    bad = good.copy()
    bad["resolution_notes"] = "fixed"
    bad["reopened"] = True
    assert score_record(good, False).score > score_record(bad, False).score
    assert "reopened_after_fix" in score_record(bad, False).flags
    assert score_record(good, True).score < score_record(good, False).score  # contradiction lowers the score
