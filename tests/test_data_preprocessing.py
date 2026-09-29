"""Data preprocessing: loaders, timestamp repair, placeholders, provenance, category correction, chunking."""
import numpy as np
import pandas as pd

from backend.data_pipeline.chunking import LONG_TEXT_WORDS, build_documents, split_sentences
from backend.data_pipeline.cleaning import (
    NOT_SET, classify_handle_time, closure_class, normalize_itil_level, normalize_placeholder, parse_dayfirst,
)
from backend.data_pipeline.loaders import detect_sources
from backend.data_pipeline.schema import TRACKED_FIELDS
from backend.data_pipeline.transform import transform_structured, transform_text_rich


def structured_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "CI_Name": ["SBA000001", "LAP000002", "SBA000003"], "CI_Cat": ["application", "computer", None],
        "CI_Subcat": ["Server Based Application", "Laptop", None], "WBS": ["W1", "W2", "W3"],
        "Incident_ID": ["IM1", "IM2", "IM3"], "Status": ["Closed", "Closed", "Work in progress"],
        "Impact": ["4", "NS", "2"], "Urgency": ["4", "3", "5 - Very Low"], "Priority": [4.0, np.nan, 3.0],
        "number_cnt": [0.1, 0.2, 0.3], "Category": ["incident", "incident", "request for information"],
        "KB_number": ["KM1", "KM2", "KM1"], "Alert_Status": ["closed"] * 3, "No_of_Reassignments": [0, 3, np.nan],
        "Open_Time": ["5/2/2012 13:32", "29-03-2012 12:36", "13-01-2014 08:00"],
        "Reopen_Time": [None, "30-03-2012 10:00", None],
        "Resolved_Time": ["6/2/2012 13:32", "29-03-2012 18:36", None],
        "Close_Time": ["6/2/2012 13:33", "29-03-2012 18:40", "14-01-2014 08:00"],
        "Handle_Time_hrs": ["3,87,16,91,111", "0,862777778", "x"], "Closure_Code": ["Software", "Overig", None],
        "No_of_Related_Interactions": [1, 1, 1], "Related_Interaction": ["SD1", "#MULTIVALUE", "#N/B"],
        "No_of_Related_Incidents": [np.nan, 1, np.nan], "No_of_Related_Changes": [np.nan, np.nan, 1],
        "Related_Change": [None, None, "C0001"],
    })


def test_dayfirst_parsing_handles_both_separators():
    s = parse_dayfirst(pd.Series(["5/2/2012 13:32", "29-03-2012 12:36", None]))
    assert s.iloc[0] == pd.Timestamp("2012-02-05 13:32")  # day-first, not May 2nd
    assert s.iloc[1] == pd.Timestamp("2012-03-29 12:36")
    assert pd.isna(s.iloc[2])


def test_handle_time_corruption_is_classified_not_trusted():
    assert classify_handle_time("3,87,16,91,111") == "corrupted_digit_grouping"
    assert classify_handle_time("0,862777778") == "decimal_comma"
    assert classify_handle_time(None) == "missing"


def test_placeholders_become_explicit_values():
    assert normalize_itil_level("NS") == NOT_SET
    assert normalize_itil_level(np.nan) == NOT_SET
    assert normalize_itil_level("5 - Very Low") == "5"
    assert normalize_itil_level(4.0) == "4"
    assert normalize_placeholder("#MULTIVALUE") == "Multiple"
    assert normalize_placeholder("#N/B") == "Not Available"
    assert closure_class("Software") == "software_fix" and closure_class("User error") == "user_or_operator"


def test_structured_transform_recomputes_durations_and_tracks_provenance():
    out = transform_structured(structured_frame(), "b.csv")
    assert len(out) == 3  # no rows dropped
    assert out.loc[0, "resolution_hours"] == 24.0  # recomputed from timestamps, not Handle_Time_hrs
    assert out.loc[0, "resolution_hours_source"] == "derived"
    assert out.loc[1, "impact"] == NOT_SET and out.loc[1, "impact_source"] == "original"
    assert out.loc[1, "closure_code"] == "Other" and out.loc[1, "closure_code_original"] == "Overig"
    assert bool(out.loc[1, "reopened"]) is True and out.loc[1, "reopened_source"] == "derived"
    assert out.loc[2, "resolution_hours_source"] == "missing"
    assert out.loc[0, "description_source"] == "missing" and out.loc[0, "description"] is None
    for f in TRACKED_FIELDS:
        assert set(out[f"{f}_source"]) <= {"original", "derived", "synthetic", "missing"}


def test_priority_matrix_consistency_flag():
    out = transform_structured(structured_frame(), "b.csv")
    assert out.loc[0, "priority_consistent"] == True  # noqa: E712  priority 4 == min(4, 4)
    assert out.loc[2, "priority_consistent"] == False  # noqa: E712  priority 3 != min(2, 5)


def test_text_rich_category_contradiction_is_corrected_but_original_kept():
    df = pd.DataFrame({"Media Asset": ["M1", "M2"], "Category": ["Hardware", "Storage"], "Ticket ID": ["T1", "T2"],
                       "Incident ID": ["INC-1", "INC-2"], "Incident Details": ["Database Timeout", "Disk Space Alert"],
                       "Description": ["Queries timing out during peak usage", "Storage exceeded threshold causing upload failures"],
                       "Solution": ["Add indexes", "Archive old files"]})
    out = transform_text_rich(df, "a.xlsx")
    assert out.loc[0, "category_original"] == "Hardware"
    assert out.loc[0, "category"] == "Database" and bool(out.loc[0, "category_conflict"])
    assert out.loc[0, "category_source"] == "derived"
    assert out.loc[1, "category"] == "Storage" and not bool(out.loc[1, "category_conflict"])
    assert out.loc[0, "description_source"] == "original"
    assert out.loc[0, "open_time_source"] == "missing"  # nothing invented


def test_sources_are_detected_by_content_not_filename(tmp_path):
    structured_frame().to_csv(tmp_path / "incidents_text.csv", index=False)  # misleading name, like the real file
    pd.DataFrame({"Incident ID": ["INC-1"], "Incident Details": ["Disk Space Alert"],
                  "Description": ["Storage exceeded threshold causing failures"],
                  "Solution": ["Archive old files and expand storage"]}).to_excel(tmp_path / "incidents_structured.xlsx", index=False)
    found = detect_sources(tmp_path)
    assert found["structured"].path.name == "incidents_text.csv"
    assert found["text_rich"].path.name == "incidents_structured.xlsx"


def test_one_incident_one_chunk_and_sentence_split_only_for_long_text():
    base = {"category": "Application", "ci_subcategory": "Web Based Application", "severity": "low",
            "impact_scope": "team", "title": "Slow app", "resolution_notes": "Restarted the service."}
    short = pd.DataFrame([{**base, "incident_id": "A", "description": "The app is slow. It freezes."}])
    docs = build_documents(short)
    assert len(docs) == 1 and docs.iloc[0]["chunk_id"] == "A#0"
    assert "Category: Application" in docs.iloc[0]["text"] and "Resolution:" in docs.iloc[0]["text"]
    long_desc = " ".join(f"Sentence number {i} describes one more symptom of the incident." for i in range(60))
    assert len(long_desc.split()) > LONG_TEXT_WORDS
    docs = build_documents(pd.DataFrame([{**base, "incident_id": "B", "description": long_desc}]))
    assert len(docs) > 1
    assert all(t.rstrip().endswith(".") for t in split_sentences(long_desc))  # never cut mid-sentence
