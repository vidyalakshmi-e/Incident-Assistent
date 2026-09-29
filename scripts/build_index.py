"""Phase 2 — Knowledge Quality Manager + embeddings + ChromaDB + SQL load.

Usage: python scripts/build_index.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.config.settings import get_settings  # noqa: E402
import argparse  # noqa: E402

from backend.database.session import init_db, reset_db, session_scope  # noqa: E402
from backend.knowledge.indexer import chunk_metadata, load_incidents, load_quality  # noqa: E402
from backend.knowledge.quality import assess, mask_entities  # noqa: E402
from backend.retrieval.embeddings import EmbeddingService  # noqa: E402
from backend.retrieval.vector_store import ChromaStore  # noqa: E402


FRESH = False


def main() -> None:
    s = get_settings()
    proc = s.processed_dir
    t0 = time.time()
    unified = pd.read_parquet(proc / "incidents_unified.parquet")
    chunks = pd.read_parquet(proc / "kb_chunks.parquet")
    kb = unified[unified["in_kb"]].reset_index(drop=True)

    emb = EmbeddingService()
    print(f"embedding provider: {emb.name}")
    doc_emb = emb.embed(chunks["text"].tolist())
    desc_emb = emb.embed((kb["title"] + ". " + kb["description"]).tolist())
    res_emb = emb.embed(kb["resolution_notes"].fillna("").tolist())
    # entity-masked variants for the Quality Manager's consistency check
    desc_m = emb.embed([mask_entities(f"{t}. {d}", c) for t, d, c in zip(kb["title"], kb["description"], kb["ci_name"])])
    res_m = emb.embed([mask_entities(r, c) for r, c in zip(kb["resolution_notes"].fillna(""), kb["ci_name"])])
    t_emb = time.time()

    # One incident = one chunk here, so chunk order == kb order; assert it rather than assume it.
    assert chunks["incident_id"].tolist() == kb["incident_id"].tolist(), "chunk/incident order mismatch"
    quality, qmeta = assess(kb, desc_m, res_m, doc_emb)
    kb_records = kb.merge(quality, on="incident_id")
    kb_records.to_parquet(proc / "kb_records.parquet", index=False)
    np.save(proc / "emb_doc.npy", doc_emb)
    np.save(proc / "emb_desc.npy", desc_emb)
    np.save(proc / "emb_res.npy", res_emb)
    np.save(proc / "emb_res_masked.npy", res_m)
    np.save(proc / "emb_desc_masked.npy", desc_m)
    (proc / "embedding_meta.json").write_text(json.dumps({
        "embedder": emb.name, "ids": kb["incident_id"].tolist(), "quality_meta": qmeta}), encoding="utf-8")

    reset_db() if FRESH else init_db()
    with session_scope() as sess:
        n = load_incidents(sess, unified)
        load_quality(sess, quality)
    t_sql = time.time()

    store = ChromaStore()
    store.reset()
    qmap = quality.set_index("incident_id").to_dict(orient="index")
    rows = kb.set_index("incident_id").to_dict(orient="index")
    metas = [chunk_metadata({"incident_id": iid, **rows[iid]}, qmap[iid]) for iid in chunks["incident_id"]]
    store.upsert(chunks["chunk_id"].tolist(), doc_emb, chunks["text"].tolist(), metas, emb.name)
    t_vec = time.time()

    print(json.dumps({
        "incidents_in_sql": n, "kb_records": len(kb_records), "chroma_vectors": store.count(),
        "quality_tiers": quality["quality_tier"].value_counts().to_dict(),
        "quality_meta": qmeta,
        "timings_s": {"embedding": round(t_emb - t0, 1), "quality+sql": round(t_sql - t_emb, 1),
                      "chroma": round(t_vec - t_sql, 1)},
    }, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="drop and recreate all SQL tables (sessions, feedback, ...)")
    FRESH = ap.parse_args().fresh
    main()
