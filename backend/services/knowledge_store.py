"""In-memory view of the knowledge base used at query time.

Base records come from `data/processed/kb_records.parquet` (built by scripts/build_index.py).
Records accepted by the Knowledge Base Evolution loop are persisted in SQL (origin=kb_evolution)
and merged in at start-up, so the KB survives restarts.
"""
from __future__ import annotations

import logging
from datetime import datetime

import numpy as np
import pandas as pd

from backend.config.settings import Settings, get_settings
from backend.data_pipeline.chunking import build_documents
from backend.schemas.retrieval import RetrievalFilters

log = logging.getLogger(__name__)

META_FIELDS = ["category", "ci_name", "ci_group", "ci_subcategory", "priority", "impact", "urgency", "status",
               "closure_code", "closure_class", "severity", "impact_scope", "suggested_team", "source", "open_time",
               "resolved_time", "resolution_hours", "reopened", "no_of_reassignments", "related_change", "kb_number",
               "text_generator"]


class KnowledgeStore:
    def __init__(self, settings: Settings | None = None, records: pd.DataFrame | None = None,
                 chunks: pd.DataFrame | None = None):
        self.s = settings or get_settings()
        if records is None:
            records = pd.read_parquet(self.s.processed_dir / "kb_records.parquet")
        if chunks is None:
            chunks = pd.read_parquet(self.s.processed_dir / "kb_chunks.parquet")
        self.records = records.reset_index(drop=True)
        self.chunks = chunks.reset_index(drop=True)
        self._reindex()

    # -------------------------------------------------------------- indexing helpers
    def _reindex(self) -> None:
        self.by_id = {r["incident_id"]: r for r in self.records.to_dict(orient="records")}
        self.chunk_incident = self.chunks["incident_id"].to_numpy()
        self.chunk_pos = {c: i for i, c in enumerate(self.chunks["chunk_id"])}
        rec = self.records.set_index("incident_id")
        ci = self.chunks["incident_id"]
        self._chunk_meta = pd.DataFrame({
            "priority": ci.map(rec["priority"]).astype(str).values,
            "impact": ci.map(rec["impact"]).astype(str).values,
            "urgency": ci.map(rec["urgency"]).astype(str).values,
            "status": ci.map(rec["status"]).astype(str).values,
            "category": ci.map(rec["category"]).astype(str).values,
            "team": ci.map(rec["suggested_team"]).astype(str).values,
            "ci_group": ci.map(rec["ci_group"]).astype(str).values,
            "source": ci.map(rec["source"]).astype(str).values,
            "text_provenance": ci.map(rec["description_source"]).astype(str).values,
            "open_time": pd.to_datetime(ci.map(rec["open_time"])).values,
            "quality": ci.map(rec["quality_score"]).astype(float).values,
            "canonical": ci.map(rec["canonical"]).fillna(True).astype(bool).values,
        })
        self.groups: dict[str, list[str]] = {}
        for iid, g in zip(self.records["incident_id"], self.records["dup_group"].fillna(self.records["incident_id"])):
            self.groups.setdefault(str(g), []).append(iid)

    def __len__(self) -> int:
        return len(self.records)

    def get(self, incident_id: str) -> dict | None:
        return self.by_id.get(incident_id)

    def duplicates_of(self, incident_id: str) -> list[str]:
        g = self.by_id[incident_id].get("dup_group") or incident_id
        return [i for i in self.groups.get(str(g), []) if i != incident_id]

    def chunk_text(self, chunk_id: str) -> str:
        return str(self.chunks.at[self.chunk_pos[chunk_id], "text"])

    # -------------------------------------------------------------- filtering
    def filter_mask(self, f: RetrievalFilters | None, canonical_only: bool = False) -> np.ndarray | None:
        m = self._chunk_meta
        if (f is None or f.is_empty()) and not canonical_only:
            return None
        mask = m["canonical"].to_numpy().copy() if canonical_only else np.ones(len(m), dtype=bool)
        if f is None:
            return mask
        for field in ("priority", "impact", "urgency", "status", "category", "team", "ci_group", "source",
                      "text_provenance"):
            vals = getattr(f, field)
            if vals:
                mask &= m[field].isin([str(v) for v in vals]).to_numpy()
        if f.time_from:
            mask &= (m["open_time"] >= np.datetime64(f.time_from)).to_numpy()
        if f.time_to:
            mask &= (m["open_time"] <= np.datetime64(f.time_to)).to_numpy()
        if f.min_quality is not None:
            mask &= (m["quality"] >= f.min_quality).to_numpy()
        if f.exclude_incident_ids:
            mask &= ~np.isin(self.chunk_incident, list(f.exclude_incident_ids))
        return mask

    @staticmethod
    def chroma_where(f: RetrievalFilters | None, canonical_only: bool = False) -> dict | None:
        conds: list[dict] = [{"canonical": True}] if canonical_only else []
        if f is None or f.is_empty():
            return conds[0] if conds else None
        mapping = {"priority": "priority", "impact": "impact", "urgency": "urgency", "status": "status",
                   "category": "category", "team": "team", "ci_group": "ci_group", "source": "source",
                   "text_provenance": "text_source"}
        for field, key in mapping.items():
            vals = getattr(f, field)
            if vals:
                conds.append({key: {"$in": [str(v) for v in vals]}})
        if f.time_from:
            conds.append({"open_ts": {"$gte": int(f.time_from.timestamp())}})
        if f.time_to:
            conds.append({"open_ts": {"$lte": int(f.time_to.timestamp())}})
        if f.min_quality is not None:
            conds.append({"quality": {"$gte": float(f.min_quality)}})
        if f.exclude_incident_ids:
            conds.append({"incident_id": {"$nin": list(f.exclude_incident_ids)}})
        if not conds:
            return None
        return conds[0] if len(conds) == 1 else {"$and": conds}

    # -------------------------------------------------------------- evolution
    def add_record(self, record: dict) -> pd.DataFrame:
        """Add one accepted record; returns its chunk rows (for vector + BM25 indexing)."""
        row = pd.DataFrame([record])
        new_chunks = build_documents(row)
        self.records = pd.concat([self.records, row], ignore_index=True)
        self.chunks = pd.concat([self.chunks, new_chunks], ignore_index=True)
        self._reindex()
        return new_chunks

    def metadata_view(self, incident_id: str) -> dict:
        r = self.by_id[incident_id]
        out = {}
        for f in META_FIELDS:
            v = r.get(f)
            if isinstance(v, (pd.Timestamp, datetime)):
                v = None if pd.isna(v) else pd.Timestamp(v).isoformat()
            elif isinstance(v, float) and np.isnan(v):
                v = None
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            out[f] = v
        return out

    def provenance_view(self, incident_id: str) -> dict:
        r = self.by_id[incident_id]
        return {f: str(r.get(f"{f}_source", "missing")) for f in (
            "title", "description", "resolution_notes", "category", "priority", "impact", "urgency",
            "closure_code", "open_time", "resolution_hours", "severity", "impact_scope")}
