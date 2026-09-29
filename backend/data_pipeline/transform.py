"""Map each real source onto the unified schema with field-level provenance."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from backend.config.taxonomy import (
    CATEGORY_TEAM, CI_GROUP_CATEGORY, CI_GROUP_TEAM, CI_SUBCAT_GROUP, infer_category, infer_severity,
)
from backend.data_pipeline.cleaning import (
    CLOSURE_TRANSLATIONS, IMPACT_SCOPE, NOT_SET, PRIORITY_SEVERITY, UNKNOWN, classify_handle_time,
    closure_class, normalize_itil_level, normalize_placeholder, parse_dayfirst,
)
from backend.data_pipeline.schema import TRACKED_FIELDS, UNIFIED_COLUMNS


def _src(mask_present: pd.Series, when_present: str) -> pd.Series:
    return pd.Series(np.where(mask_present, when_present, "missing"), index=mask_present.index)


def transform_structured(df: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Source B (structured event log) → unified schema. No text here; text comes later."""
    out = pd.DataFrame(index=df.index)
    out["incident_id"] = df["Incident_ID"].astype(str)
    out["source"] = "B_event_log"
    out["source_file"] = file_name
    out["source_row"] = df.index.astype(int)
    out["ticket_id"] = None

    out["ticket_type"] = df["Category"].astype(str)
    out["ticket_type_source"] = "original"

    out["ci_name"] = df["CI_Name"].astype(str)
    out["ci_name_source"] = "original"
    out["ci_category"] = df["CI_Cat"].fillna(UNKNOWN)
    out["ci_category_source"] = _src(df["CI_Cat"].notna(), "original")
    out["ci_subcategory"] = df["CI_Subcat"].fillna(UNKNOWN)
    out["ci_subcategory_source"] = _src(df["CI_Subcat"].notna(), "original")
    out["ci_group"] = df["CI_Subcat"].map(CI_SUBCAT_GROUP).fillna("other")
    out["wbs"] = df["WBS"]
    out["media_asset"] = None

    # Source B has no domain category; its "Category" column is the ticket type.
    out["category"] = out["ci_group"].map(CI_GROUP_CATEGORY).fillna(UNKNOWN)
    out["category_source"] = np.where(out["category"] == UNKNOWN, "missing", "derived")
    out["category_original"] = None
    out["category_conflict"] = False

    for col, src in (("impact", "Impact"), ("urgency", "Urgency"), ("priority", "Priority")):
        out[col] = df[src].map(normalize_itil_level)
        out[f"{col}_source"] = "original"  # "NS"/NaN re-labelled "Not Set" — still the source's value
    iu = pd.concat([pd.to_numeric(out["impact"], errors="coerce"),
                    pd.to_numeric(out["urgency"], errors="coerce")], axis=1).min(axis=1)
    pr = pd.to_numeric(out["priority"], errors="coerce")
    out["priority_consistent"] = np.where(pr.notna() & iu.notna(), pr == iu, None)
    out["severity"] = out["priority"].map(PRIORITY_SEVERITY).fillna(UNKNOWN)
    out["severity_source"] = np.where(out["severity"] == UNKNOWN, "missing", "derived")
    out["impact_scope"] = out["impact"].map(IMPACT_SCOPE).fillna(UNKNOWN)
    out["impact_scope_source"] = np.where(out["impact_scope"] == UNKNOWN, "missing", "derived")

    out["status"] = df["Status"]
    out["status_source"] = "original"
    out["closure_code_original"] = df["Closure_Code"]
    out["closure_code"] = df["Closure_Code"].map(lambda v: CLOSURE_TRANSLATIONS.get(v, v)).fillna(NOT_SET)
    out["closure_code_source"] = "original"
    out["closure_class"] = out["closure_code"].map(closure_class)
    out["closure_class_source"] = "derived"

    for col, src in (("open_time", "Open_Time"), ("resolved_time", "Resolved_Time"),
                     ("reopen_time", "Reopen_Time"), ("close_time", "Close_Time")):
        out[col] = parse_dayfirst(df[src])
        out[f"{col}_source"] = _src(out[col].notna(), "original")

    out["resolution_hours"] = (out["resolved_time"] - out["open_time"]).dt.total_seconds() / 3600
    out["resolution_hours_source"] = _src(out["resolution_hours"].notna(), "derived")
    out["close_hours"] = (out["close_time"] - out["open_time"]).dt.total_seconds() / 3600
    out["handle_time_raw"] = df["Handle_Time_hrs"].astype("string")
    out["handle_time_status"] = df["Handle_Time_hrs"].map(classify_handle_time)

    out["reopened"] = out["reopen_time"].notna()
    out["reopened_source"] = "derived"
    out["no_of_reassignments"] = df["No_of_Reassignments"]
    out["no_of_reassignments_source"] = _src(df["No_of_Reassignments"].notna(), "original")
    out["no_of_related_interactions"] = df["No_of_Related_Interactions"]
    out["related_interaction"] = df["Related_Interaction"].map(normalize_placeholder)
    out["no_of_related_incidents"] = df["No_of_Related_Incidents"]
    out["no_of_related_changes"] = df["No_of_Related_Changes"]
    out["related_change"] = df["Related_Change"].map(normalize_placeholder)
    out["kb_number"] = df["KB_number"]

    for f in ("title", "description", "resolution_notes"):
        out[f] = None
        out[f"{f}_source"] = "missing"
    out["in_kb"] = False
    out["text_generator"] = None
    out["suggested_team"] = out["ci_group"].map(CI_GROUP_TEAM)
    out["suggested_team_source"] = np.where(out["suggested_team"].notna(), "derived", "missing")
    for g in ("gt_scenario", "gt_strategy", "gt_view", "gt_note_quality", "gt_seeded_defect"):
        out[g] = None
    return finalize(out)


def _slug(s: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "-", s.upper()).strip("-")


def transform_text_rich(df: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Source A (text-rich) → unified schema. Its Category column is kept as `category_original`;
    the corrected category is derived from the text because profiling found it misaligned."""
    out = pd.DataFrame(index=df.index)
    out["incident_id"] = df["Incident ID"].astype(str)
    out["source"] = "A_text_rich"
    out["source_file"] = file_name
    out["source_row"] = df.index.astype(int)
    out["ticket_id"] = df["Ticket ID"].astype(str)
    out["ticket_type"] = "incident"  # sheet is named "Incident Data"
    out["ticket_type_source"] = "derived"

    out["ci_name"] = df["Media Asset"].astype(str)
    out["ci_name_source"] = "original"
    out["media_asset"] = df["Media Asset"].astype(str)
    out["ci_category"] = UNKNOWN
    out["ci_category_source"] = "missing"
    out["ci_subcategory"] = UNKNOWN
    out["ci_subcategory_source"] = "missing"
    out["ci_group"] = "media"
    out["wbs"] = None

    out["title"] = df["Incident Details"].astype(str)
    out["description"] = df["Description"].astype(str)
    out["resolution_notes"] = df["Solution"].astype(str)
    for f in ("title", "description", "resolution_notes"):
        out[f"{f}_source"] = "original"

    cats, conflicts = [], []
    for orig, title, desc in zip(df["Category"], df["Incident Details"], df["Description"]):
        inferred, scores = infer_category(f"{title}. {desc}")
        conflict = inferred is not None and inferred != orig and scores.get(orig, 0) == 0
        cats.append(inferred if conflict else orig)
        conflicts.append(conflict)
    out["category_original"] = df["Category"].astype(str)
    out["category"] = cats
    out["category_conflict"] = conflicts
    out["category_source"] = np.where(conflicts, "derived", "original")

    for col in ("impact", "urgency", "priority"):
        out[col] = NOT_SET
        out[f"{col}_source"] = "missing"
    out["priority_consistent"] = None
    sev = [infer_severity(f"{t}. {d}") for t, d in zip(df["Incident Details"], df["Description"])]
    out["severity"] = [s or UNKNOWN for s in sev]
    out["severity_source"] = ["derived" if s else "missing" for s in sev]
    out["impact_scope"] = UNKNOWN
    out["impact_scope_source"] = "missing"
    out["status"] = UNKNOWN
    out["status_source"] = "missing"
    out["closure_code"] = NOT_SET
    out["closure_code_original"] = None
    out["closure_code_source"] = "missing"
    out["closure_class"] = UNKNOWN
    out["closure_class_source"] = "missing"
    for col in ("open_time", "resolved_time", "reopen_time", "close_time"):
        out[col] = pd.NaT
        out[f"{col}_source"] = "missing"
    out["resolution_hours"] = np.nan
    out["resolution_hours_source"] = "missing"
    out["close_hours"] = np.nan
    out["handle_time_raw"] = None
    out["handle_time_status"] = "missing"
    out["reopened"] = None
    out["reopened_source"] = "missing"
    out["no_of_reassignments"] = np.nan
    out["no_of_reassignments_source"] = "missing"
    for col in ("no_of_related_interactions", "no_of_related_incidents", "no_of_related_changes"):
        out[col] = np.nan
    for col in ("related_interaction", "related_change", "kb_number"):
        out[col] = None
    out["in_kb"] = True
    out["text_generator"] = "source"
    out["suggested_team"] = out["category"].map(CATEGORY_TEAM)
    out["suggested_team_source"] = "derived"
    out["gt_scenario"] = "SA-" + df["Incident Details"].map(_slug)
    out["gt_strategy"] = "SA-" + df["Solution"].map(_slug).str[:40]
    out["gt_view"] = "source"
    out["gt_note_quality"] = "detailed"
    out["gt_seeded_defect"] = np.where(conflicts, "category_conflict (real)", "")
    return finalize(out)


def finalize(out: pd.DataFrame) -> pd.DataFrame:
    for c in UNIFIED_COLUMNS:
        if c not in out.columns:
            out[c] = None
    for f in TRACKED_FIELDS:
        bad = set(out[f"{f}_source"].unique()) - {"original", "derived", "synthetic", "missing"}
        assert not bad, f"invalid provenance for {f}: {bad}"
    return out[UNIFIED_COLUMNS].reset_index(drop=True)
