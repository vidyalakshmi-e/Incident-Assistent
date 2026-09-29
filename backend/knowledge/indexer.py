"""Load the processed dataset into SQL and build the vector index."""
from __future__ import annotations

import logging
import math
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import delete

from backend.data_pipeline.schema import TRACKED_FIELDS
from backend.models.entities import Incident, KnowledgeQuality

log = logging.getLogger(__name__)

GT_FIELDS = ["gt_scenario", "gt_strategy", "gt_view", "gt_note_quality", "gt_seeded_defect"]
SQL_FIELDS = [
    "incident_id", "source", "source_file", "ticket_id", "ticket_type", "category", "category_original",
    "category_conflict", "ci_name", "ci_category", "ci_subcategory", "ci_group", "impact", "urgency",
    "priority", "severity", "impact_scope", "status", "closure_code", "closure_class", "open_time",
    "resolved_time", "reopen_time", "close_time", "resolution_hours", "reopened", "no_of_reassignments",
    "no_of_related_incidents", "related_change", "kb_number", "title", "description", "resolution_notes",
    "in_kb", "text_generator", "suggested_team",
]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.to_pydatetime()
    if v is pd.NaT:
        return None
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def incident_mapping(r: dict, origin: str = "dataset") -> dict:
    m = {f: _clean(r.get(f)) for f in SQL_FIELDS}
    m["category_conflict"] = bool(m["category_conflict"]) if m["category_conflict"] is not None else False
    m["in_kb"] = bool(m["in_kb"])
    m["origin"] = origin
    m["provenance"] = {f: r.get(f"{f}_source", "missing") for f in TRACKED_FIELDS}
    m["ground_truth"] = {g: _clean(r.get(g)) for g in GT_FIELDS if _clean(r.get(g))}
    m["created_at"] = datetime.utcnow()
    return m


def load_incidents(session, unified: pd.DataFrame) -> int:
    session.execute(delete(Incident))
    recs = unified.to_dict(orient="records")
    for i in range(0, len(recs), 5000):
        session.bulk_insert_mappings(Incident, [incident_mapping(r) for r in recs[i:i + 5000]])
    return len(recs)


def load_quality(session, quality: pd.DataFrame) -> None:
    session.execute(delete(KnowledgeQuality))
    session.bulk_insert_mappings(KnowledgeQuality, [{
        "incident_id": q["incident_id"], "score": float(q["quality_score"]), "tier": q["quality_tier"],
        "flags": list(q["quality_flags"]), "components": dict(q["quality_components"]),
        "dup_group": q["dup_group"], "near_dup_group": q["near_dup_group"],
        "canonical": bool(q["canonical"]), "review_status": "auto", "updated_at": datetime.utcnow(),
    } for q in quality.to_dict(orient="records")])


def chunk_metadata(row: dict, q: dict) -> dict:
    ts = row.get("open_time")
    return {
        "incident_id": row["incident_id"],
        "category": str(row.get("category") or "Unknown"),
        "ci_group": str(row.get("ci_group") or "other"),
        "priority": str(row.get("priority") or "Not Set"),
        "impact": str(row.get("impact") or "Not Set"),
        "urgency": str(row.get("urgency") or "Not Set"),
        "status": str(row.get("status") or "Unknown"),
        "severity": str(row.get("severity") or "Unknown"),
        "source": str(row.get("source")),
        "text_source": str(row.get("description_source") or "missing"),
        "team": str(row.get("suggested_team") or "Unknown"),
        "open_ts": int(pd.Timestamp(ts).timestamp()) if ts is not None and not pd.isna(ts) else 0,
        "quality": float(q.get("quality_score", 0.0)),
        "canonical": bool(q.get("canonical", True)),
        "dup_group": str(q.get("dup_group", row["incident_id"])),
    }


def ensure_vector_index(rt) -> dict:
    """Make sure the vector store holds every chunk of the in-memory KB.

    Used at API / worker start-up (e.g. a fresh ChromaDB server in http mode): base vectors
    are loaded from `emb_doc.npy` produced by build_index.py, so no GPU or re-embedding is needed;
    only KB-evolution additions are embedded on the fly."""
    import json

    from backend.retrieval.vector_store import VectorStoreUnavailable

    try:
        have = rt.vectors.count()
    except VectorStoreUnavailable as exc:
        return {"status": "unavailable", "detail": str(exc)}
    need = len(rt.store.chunks)
    if have >= need:
        return {"status": "ok", "vectors": have}
    proc = rt.s.processed_dir
    chunks = pd.read_parquet(proc / "kb_chunks.parquet")
    meta = json.loads((proc / "embedding_meta.json").read_text(encoding="utf-8"))
    emb = np.load(proc / "emb_doc.npy")
    if meta["embedder"] != rt.embedder.name:
        emb = rt.embedder.embed(chunks["text"].tolist())
    recs = rt.store.records.set_index("incident_id")
    quality = {"quality_score": 0.0, "canonical": True}
    metas = []
    for iid in chunks["incident_id"]:
        r = recs.loc[iid].to_dict()
        metas.append(chunk_metadata({"incident_id": iid, **r}, {"quality_score": r.get("quality_score", 0.0),
                                                                "canonical": r.get("canonical", True),
                                                                "dup_group": r.get("dup_group", iid)}))
    rt.vectors.upsert(chunks["chunk_id"].tolist(), emb, chunks["text"].tolist(), metas, rt.embedder.name)
    extra = rt.store.chunks[~rt.store.chunks["chunk_id"].isin(chunks["chunk_id"])]
    if len(extra):
        vecs = rt.embedder.embed(extra["text"].tolist())
        metas = [chunk_metadata({"incident_id": i, **recs.loc[i].to_dict()}, {**quality, "dup_group": i})
                 for i in extra["incident_id"]]
        rt.vectors.upsert(extra["chunk_id"].tolist(), vecs, extra["text"].tolist(), metas, rt.embedder.name)
    rt.retriever._check_vector_embedder()
    return {"status": "loaded", "vectors": rt.vectors.count()}
