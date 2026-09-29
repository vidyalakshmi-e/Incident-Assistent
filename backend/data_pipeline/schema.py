"""Unified target schema (DATASET Step 2) with field-level provenance.

Provenance values (per field, stored in a companion `<field>_source` column):
    original  — value taken directly from a source file (possibly re-labelled, e.g. "NS" → "Not Set")
    derived   — computed from other real fields by a documented rule
    synthetic — generated (LLM or conditioned template) because no real value existed
    missing   — no value exists and none was invented

Taint rule: a value derived *from synthetic input* is itself tagged "synthetic".
"""
from __future__ import annotations

PROVENANCE_VALUES = ("original", "derived", "synthetic", "missing")

# Fields that carry a companion `<field>_source` column.
TRACKED_FIELDS = [
    "ticket_type", "category", "ci_name", "ci_category", "ci_subcategory",
    "impact", "urgency", "priority", "severity", "impact_scope", "status", "closure_code",
    "closure_class", "open_time", "resolved_time", "reopen_time", "close_time",
    "resolution_hours", "reopened", "no_of_reassignments",
    "title", "description", "resolution_notes", "suggested_team",
]

UNIFIED_COLUMNS = [
    # identity
    "incident_id", "source", "source_file", "source_row", "ticket_id",
    # classification
    "ticket_type", "category", "category_original", "category_conflict",
    "ci_name", "ci_category", "ci_subcategory", "ci_group", "wbs", "media_asset",
    # ITIL
    "impact", "urgency", "priority", "priority_consistent", "severity", "impact_scope",
    "status", "closure_code", "closure_code_original", "closure_class",
    # time
    "open_time", "resolved_time", "reopen_time", "close_time",
    "resolution_hours", "close_hours", "handle_time_raw", "handle_time_status",
    # outcome / relationships
    "reopened", "no_of_reassignments", "no_of_related_interactions", "related_interaction",
    "no_of_related_incidents", "no_of_related_changes", "related_change", "kb_number",
    # text
    "title", "description", "resolution_notes", "in_kb", "text_generator",
    # routing (derived)
    "suggested_team",
    # evaluation-only ground truth from the generator (never read by runtime features)
    "gt_scenario", "gt_strategy", "gt_view", "gt_note_quality", "gt_seeded_defect",
] + [f"{f}_source" for f in TRACKED_FIELDS]
