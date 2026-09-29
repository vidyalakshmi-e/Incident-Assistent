"""Phase 1 orchestration: inspect → transform → merge → conditioned synthetic text → report."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config.settings import get_settings
from backend.data_pipeline.chunking import build_documents
from backend.data_pipeline.loaders import detect_sources
from backend.data_pipeline.profiling import (
    EXPECTED_STRUCTURED_FIELDS, EXPECTED_TEXT_FIELDS, compare_expected, profile_frame,
)
from backend.data_pipeline.scenarios import NOVEL_PROBES
from backend.data_pipeline.schema import TRACKED_FIELDS
from backend.data_pipeline.synthetic import TemplateVerbalizer, plan_synthetic_rows
from backend.data_pipeline.transform import transform_structured, transform_text_rich

log = logging.getLogger(__name__)

DERIVED_COLUMNS = [
    "category (Source B, from CI_Subcat)", "category (Source A, corrected from text)",
    "category_conflict", "ci_group", "priority_consistent", "severity", "impact_scope",
    "closure_class", "resolution_hours", "close_hours", "handle_time_status", "reopened",
    "suggested_team", "ticket_type (Source A)",
]


def eligible_for_text(unified: pd.DataFrame) -> pd.DataFrame:
    """Real Source B rows that can carry generated text: closed incidents with a resolution
    timestamp, a known CI group and a real closure code."""
    b = unified[unified["source"] == "B_event_log"]
    return b[
        (b["status"] == "Closed") & b["resolved_time"].notna() & (b["ticket_type"] == "incident")
        & (b["ci_group"] != "other") & (b["closure_code"] != "Not Set")
    ]


def run(generator: str = "auto", llm_model: str | None = None, seed: int = 42,
        target_rows: int = 3000) -> dict:
    s = get_settings()
    raw, processed, evaldir = s.raw_dir, s.processed_dir, s.evaluation_dir
    processed.mkdir(parents=True, exist_ok=True)
    evaldir.mkdir(parents=True, exist_ok=True)

    # ---- Step 1: inspect
    sources = detect_sources(raw)
    a, b = sources["text_rich"], sources["structured"]
    profile = {
        "detected": {k: {"file": v.path.name, "reason": v.reason} for k, v in sources.items()},
        "text_rich": {**profile_frame(a.frame), "expected_vs_actual": compare_expected(a.frame, EXPECTED_TEXT_FIELDS)},
        "structured": {**profile_frame(b.frame), "expected_vs_actual": compare_expected(b.frame, EXPECTED_STRUCTURED_FIELDS)},
        "join_key_check": {
            "text_rich_id_example": str(a.frame["Incident ID"].iloc[0]),
            "structured_id_example": str(b.frame["Incident_ID"].iloc[0]),
            "overlapping_ids": int(len(set(a.frame["Incident ID"].astype(str)) & set(b.frame["Incident_ID"].astype(str)))),
            "decision": "no shared identifier — sources are processed as two independent pipelines feeding one schema",
        },
    }

    # ---- Steps 2/3/5: transform each source into the unified schema (no forced join)
    ua = transform_text_rich(a.frame, a.path.name)
    ub = transform_structured(b.frame, b.path.name)
    unified = pd.concat([ua, ub], ignore_index=True)

    # ---- Step 4: conditioned synthetic text for a stratified sample of real Source B rows
    elig = eligible_for_text(unified)
    briefs = plan_synthetic_rows(elig, seed=seed, target=target_rows)
    texts = _verbalize(briefs, generator, llm_model, processed, seed)
    idx = unified.set_index("incident_id").index
    for brief, (text, gen) in zip(briefs, texts):
        i = idx.get_loc(brief.incident_id)
        for f in ("title", "description", "resolution_notes"):
            unified.at[i, f] = text[f]
            unified.at[i, f"{f}_source"] = "synthetic"
        unified.at[i, "in_kb"] = True
        unified.at[i, "text_generator"] = gen
        unified.at[i, "gt_scenario"] = brief.scenario_id
        unified.at[i, "gt_strategy"] = brief.strategy_id
        unified.at[i, "gt_view"] = brief.view
        unified.at[i, "gt_note_quality"] = brief.note_quality
        unified.at[i, "gt_seeded_defect"] = brief.seeded_defect
    (processed / "synthetic_briefs.jsonl").write_text(
        "\n".join(json.dumps(asdict(b_)) for b_ in briefs), encoding="utf-8")

    # ---- novel probes: synthetic, evaluation-only, never indexed
    probes = [{"probe_id": f"NOVEL-{i + 1:03d}", "text": p["text"], "hard": p["hard"],
               "provenance": "synthetic", "purpose": "novel-incident detection validation (not indexed)"}
              for i, p in enumerate(NOVEL_PROBES)]
    (evaldir / "novel_probes.jsonl").write_text("\n".join(json.dumps(p) for p in probes), encoding="utf-8")

    # ---- persist
    unified.to_parquet(processed / "incidents_unified.parquet", index=False)
    kb = unified[unified["in_kb"]].copy()
    docs = build_documents(kb)
    docs.to_parquet(processed / "kb_chunks.parquet", index=False)

    report = build_report(unified, kb, docs, briefs, probes, profile)
    (processed / "profile_report.json").write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    (processed / "dataset_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def _verbalize(briefs, generator, llm_model, processed: Path, seed: int):
    from backend.data_pipeline.llm_verbalizer import LLMVerbalizer, LocalHFBatchGenerator, TextCache

    cache = TextCache(processed / "synthetic_text_cache.jsonl")
    all_cached = all(cache.get(b.key()) for b in briefs)
    if generator == "template" or (generator == "auto" and not all_cached and not llm_model):
        tv = TemplateVerbalizer()
        return [(tv.render(b), tv.name) for b in briefs]
    gen = None if all_cached else LocalHFBatchGenerator(llm_model or "Qwen/Qwen2.5-3B-Instruct", seed=seed)
    return LLMVerbalizer(gen, cache, batch_size=48).render_all(briefs)


def _prov_table(df: pd.DataFrame) -> dict:
    out = {}
    for f in TRACKED_FIELDS:
        vc = df[f"{f}_source"].value_counts()
        out[f] = {k: int(vc.get(k, 0)) for k in ("original", "derived", "synthetic", "missing")}
    return out


def build_report(unified, kb, docs, briefs, probes, profile) -> dict:
    total_cells = {"original": 0, "derived": 0, "synthetic": 0, "missing": 0}
    prov = _prov_table(unified)
    for counts in prov.values():
        for k, v in counts.items():
            total_cells[k] += v
    present = sum(v for k, v in total_cells.items() if k != "missing")
    kb_prov = _prov_table(kb)
    text_cells = {k: sum(kb_prov[f][k] for f in ("title", "description", "resolution_notes"))
                  for k in ("original", "synthetic")}
    b_rows = unified[unified["source"] == "B_event_log"]
    gens = kb["text_generator"].value_counts().to_dict()
    return {
        "original_row_count": {
            "text_rich (Source A)": int((unified["source"] == "A_text_rich").sum()),
            "structured (Source B)": int(len(b_rows)),
            "total": int(len(unified)),
        },
        "rows_modified_or_deleted": 0,
        "augmented_synthetic_rows": {
            "knowledge_base": 0,
            "novel_probes (evaluation-only, not indexed)": len(probes),
            "note": "No synthetic rows were added to the knowledge base. Generated text is attached to existing real Source B rows.",
        },
        "derived_columns_added": DERIVED_COLUMNS,
        "knowledge_base": {
            "incidents": int(len(kb)),
            "chunks": int(len(docs)),
            "from_source_A_original_text": int((kb["source"] == "A_text_rich").sum()),
            "from_source_B_with_synthetic_text": int((kb["source"] == "B_event_log").sum()),
            "text_generators": {str(k): int(v) for k, v in gens.items()},
            "families_with_generated_text": sorted(kb["gt_scenario"].dropna().unique().tolist()),
            "rows_per_family": {str(k): int(v) for k, v in kb["gt_scenario"].value_counts().items()},
            "note_quality": {str(k): int(v) for k, v in kb["gt_note_quality"].value_counts().items()},
            "seeded_defects": {str(k): int(v) for k, v in kb["gt_seeded_defect"].replace("", np.nan).value_counts().items()},
            "text_field_ratio": {
                "original": text_cells["original"], "synthetic": text_cells["synthetic"],
                "synthetic_pct": round(100 * text_cells["synthetic"] / max(1, sum(text_cells.values())), 2),
            },
        },
        "field_level_provenance_all_rows": prov,
        "cell_proportions_all_rows": {
            k: round(100 * v / max(1, present), 2) for k, v in total_cells.items() if k != "missing"
        } | {"missing_cells": total_cells["missing"]},
        "field_level_provenance_kb_rows": kb_prov,
        "data_repairs": {
            "timestamps_parsed_dayfirst": int(b_rows["open_time"].notna().sum()),
            "handle_time_status": {str(k): int(v) for k, v in b_rows["handle_time_status"].value_counts().items()},
            "impact_not_set": int((b_rows["impact"] == "Not Set").sum()),
            "priority_not_set": int((b_rows["priority"] == "Not Set").sum()),
            "closure_code_not_set": int((b_rows["closure_code"] == "Not Set").sum()),
            "closure_code_translated_from_dutch": int(b_rows["closure_code_original"].isin(["Overig", "Kwaliteit van de output"]).sum()),
            "related_interaction_placeholders": {str(k): int(v) for k, v in b_rows["related_interaction"].isin(["Not Available", "Multiple"]).value_counts().items()},
            "priority_matrix_inconsistent": int((b_rows["priority_consistent"] == False).sum()),  # noqa: E712
            "closed_without_resolved_time": int(((b_rows["status"] == "Closed") & b_rows["resolved_time"].isna()).sum()),
            "source_A_category_conflicts": int(unified["category_conflict"].sum()),
        },
        "join": profile["join_key_check"],
    }
