"""Enriched fingerprint extraction + causal-chain tagging (observed / derived / inferred)."""
import pandas as pd

from backend.intelligence.causal_chain import build_family_chain, build_incident_chain
from backend.intelligence.fingerprinting import FIELDS, UNKNOWN, Fingerprinter, dimension_match


def record(**kw):
    base = {"incident_id": "IM1", "title": "Slow app", "description": "The CRM system is very slow and freezes.",
            "resolution_notes": "Heap was almost exhausted by a memory leak; recycled the application service.",
            "description_source": "synthetic", "resolution_notes_source": "synthetic", "ci_group": "app_server",
            "ci_subcategory": "Server Based Application", "closure_class": "software_fix", "closure_code": "Software",
            "impact": "3", "urgency": "2", "impact_scope": "team", "related_change": None,
            "open_time": pd.Timestamp("2014-01-01 08:00"), "resolved_time": pd.Timestamp("2014-01-01 12:00"),
            "reopen_time": None, "no_of_reassignments": 1}
    base.update(kw)
    return base


def test_query_fingerprint_extracts_fields_and_leaves_unknowns():
    fp = Fingerprinter().from_query("Since the new version was deployed, users in production cannot log in to the "
                                    "HR portal; all users are affected.")
    v = fp.values
    assert v["symptom"] == "login failure"
    assert v["trigger"] == "deployment / release"
    assert v["environment"] == "Production"
    assert v["impact_scope"] == "organization-wide"
    assert v["root_cause"] == UNKNOWN  # a new incident's root cause is not invented
    assert fp.provenance["root_cause"] == "missing"
    assert set(v) == set(FIELDS)


def test_record_fingerprint_provenance_follows_text_source():
    fp = Fingerprinter().from_record(record())
    assert fp.values["root_cause"] == "memory leak / heap exhaustion"
    assert fp.provenance["root_cause"] == "synthetic"  # derived from generated text → taint propagates
    assert fp.provenance["impact_scope"] in {"derived", "synthetic"}
    fp2 = Fingerprinter().from_record(record(description_source="original", resolution_notes_source="original"))
    assert fp2.provenance["root_cause"] == "derived"


def test_closure_code_fallback_root_cause_is_derived():
    fp = Fingerprinter().from_record(record(resolution_notes="closed", closure_class="hardware_fix",
                                            description="Something is wrong with my device"))
    assert fp.values["root_cause"] == "hardware fault (per closure code)"
    assert fp.provenance["root_cause"] == "derived"


def test_dimension_match_handles_unknown_and_family_shares():
    fp = Fingerprinter().from_query("the database queries are very slow")
    assert dimension_match(fp, {"component": "Database"}, "component") == 1.0
    assert dimension_match(fp, {"component": {"Database": 0.7}}, "component") == 0.7
    assert dimension_match(fp, {"environment": "Production"}, "environment") is None


def test_causal_chain_tags_are_assigned_by_rule():
    fp = Fingerprinter().from_record(record(related_change="C0001"))
    ch = build_incident_chain(record(related_change="C0001"), fp)
    tags = {l["stage"]: l["tag"] for l in ch["links"]}
    assert ch["available"]
    assert tags["trigger"] == "observed"  # real related-change record
    assert tags["technical_failure"] == "inferred"  # extracted from generated text
    assert tags["symptom"] == "inferred"  # generated description
    assert tags["business_impact"] == "derived"  # ITIL fields via documented rule
    assert tags["outcome"] == "observed"  # real timestamps
    assert ch["temporal_ordering"]["tag"] == "observed"


def test_original_text_links_are_observed_and_closure_code_links_derived():
    rec = record(description_source="original", resolution_notes_source="original", resolution_notes="closed")
    ch = build_incident_chain(rec, Fingerprinter().from_record(rec))
    tags = {l["stage"]: l["tag"] for l in ch["links"]}
    assert tags["symptom"] == "observed" and tags["resolution"] == "observed"
    assert tags["technical_failure"] == "derived"


def test_no_chain_is_fabricated_without_timestamps():
    rec = record(open_time=None, resolved_time=None)
    ch = build_incident_chain(rec, Fingerprinter().from_record(rec))
    assert ch["available"] is False and ch["links"] == [] and "temporal ordering" in ch["reason"]
    assert ch["facts"]  # facts are still shown, unordered


def test_family_chain_reports_insufficient_evidence_for_empty_stages():
    rec = record()
    chains = [build_incident_chain(rec, Fingerprinter().from_record(rec))]
    fam = build_family_chain(chains)
    assert [s["stage"] for s in fam][0] == "trigger"
    assert fam[0]["statement"] == "insufficient evidence"  # no trigger data
