"""Offline build of the Pattern Intelligence artefacts (Phase 4) and resolution strategies (Phase 6)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import delete, update

from backend.config.settings import Settings, get_settings
from backend.database.session import init_db, session_scope
from backend.intelligence.causal_chain import build_family_chain, build_incident_chain
from backend.intelligence.fingerprinting import Fingerprinter
from backend.intelligence.graph import family_graph, incident_edges
from backend.intelligence.pattern_detection import PatternEngine, build_families, choose_clusters, feature_matrix
from backend.intelligence.recurrence import ci_hotspots, family_recurrence, family_transitions
from backend.knowledge.quality import resolution_detail
from backend.models.entities import (
    CausalChainLink, Incident, IncidentFingerprint, IncidentPattern, IncidentRelationship, ResolutionStrategy,
)
from backend.rag.strategy import build_family_strategies

log = logging.getLogger(__name__)


def build_all(s: Settings | None = None, write_sql: bool = True) -> dict:
    s = s or get_settings()
    proc = Path(s.processed_dir)
    kb = pd.read_parquet(proc / "kb_records.parquet")
    meta = json.loads((proc / "embedding_meta.json").read_text(encoding="utf-8"))
    ids = meta["ids"]
    assert ids == kb["incident_id"].tolist(), "embedding order mismatch — rerun build_index.py"
    desc_emb = np.load(proc / "emb_desc.npy")
    res_emb = np.load(proc / "emb_res_masked.npy")

    # ---- fingerprints
    fper = Fingerprinter()
    recs = kb.to_dict(orient="records")
    fps = [fper.from_record(r) for r in recs]

    # ---- clustering
    usable = np.array([resolution_detail(r.get("resolution_notes"))[0] > 0.2 for r in recs], dtype=np.float32)
    X = feature_matrix(desc_emb, res_emb, fps, usable)
    labels, k, sweep = choose_clusters(X, seed=s.random_seed)
    families, assign = build_families(ids, kb, desc_emb, X, labels, fps)
    log.info("families: %d (k=%d)", len(families), k)

    # ---- causal chains
    chains = {r["incident_id"]: build_incident_chain(r, fp) for r, fp in zip(recs, fps)}
    rec_by_id = kb.set_index("incident_id", drop=False)
    for fam in families:
        fam.extra["causal_chain"] = build_family_chain([chains[m] for m in fam.members])
        fam.extra["recurrence"] = family_recurrence(rec_by_id.loc[fam.members])

    # ---- strategies: cluster the *action* clauses of each note (entity-masked) so that
    # "restart" and "increase heap" separate even when both notes open with the same root cause
    from backend.knowledge.quality import mask_entities
    from backend.rag.strategy import action_text
    from backend.retrieval.embeddings import EmbeddingService

    act_emb = EmbeddingService(s).embed([mask_entities(action_text(r.get("resolution_notes") or ""), r.get("ci_name"))
                                         for r in recs])
    np.save(proc / "emb_action.npy", act_emb)
    res_by_id = {i: act_emb[n] for n, i in enumerate(ids)}
    strategies, strategy_of = [], {}
    for fam in families:
        st, so = build_family_strategies(fam.family_id, rec_by_id.loc[fam.members], res_by_id)
        strategies += st
        strategy_of.update(so)
        fam.extra["n_strategies"] = len(st)

    fp_dicts = {i: fp.as_dict() for i, fp in zip(ids, fps)}
    engine = PatternEngine(families, assign, fp_dicts,
                           {"k_selected": k, "silhouette_sweep": sweep, "n_families": len(families),
                            "feature_weights": "desc 1.0, resolution 0.8, fp(root_cause .9, component .5, symptom .4, failure_type .3)"})
    engine.save(s)
    (proc / "causal_chains.json").write_text(json.dumps(chains, default=str), encoding="utf-8")
    (proc / "strategies.json").write_text(json.dumps({"strategies": strategies, "strategy_of": strategy_of}),
                                          encoding="utf-8")

    # ---- recurrence over the whole real dataset + graph
    unified = pd.read_parquet(proc / "incidents_unified.parquet",
                              columns=["incident_id", "source", "ci_name", "ci_subcategory", "open_time",
                                       "closure_code", "reopened", "priority"])
    proactive = {"ci_hotspots": ci_hotspots(unified), "family_transitions": family_transitions(kb, assign)}
    (proc / "proactive.json").write_text(json.dumps(proactive, default=str), encoding="utf-8")
    edges = incident_edges(kb)
    pd.DataFrame(edges).to_parquet(proc / "relationships.parquet", index=False) if edges else None
    fgraph = family_graph(engine.families, kb, assign)
    (proc / "family_graph.json").write_text(json.dumps(fgraph, default=str), encoding="utf-8")

    if write_sql:
        _write_sql(engine, fp_dicts, chains, strategies, edges, fper.version)
    return {"families": len(families), "k_selected": k, "strategies": len(strategies), "edges": len(edges),
            "hotspots": len(proactive["ci_hotspots"])}


def _write_sql(engine: PatternEngine, fps: dict, chains: dict, strategies: list[dict], edges: list[dict],
               version: str) -> None:
    init_db()
    with session_scope() as sess:
        for model in (IncidentFingerprint, IncidentPattern, CausalChainLink, ResolutionStrategy, IncidentRelationship):
            sess.execute(delete(model))
        sess.bulk_insert_mappings(IncidentFingerprint, [
            {"incident_id": i, **d["values"], "provenance": d["provenance"], "extractor_version": version}
            for i, d in fps.items()])
        sess.bulk_insert_mappings(IncidentPattern, [
            {"pattern_id": f.family_id, "name": f.name, "status": f.status, "size": len(f.members),
             "members_original_text": f.members_original_text, "members_synthetic_text": f.members_synthetic_text,
             "signature": f.signature, "recurrence": f.extra.get("recurrence", {}),
             "causal_chain": f.extra.get("causal_chain", []), "centroid": []}
            for f in engine.families.values()])
        links = []
        for iid, ch in chains.items():
            for pos, l in enumerate(ch["links"] or ch.get("facts", [])):
                links.append({"incident_id": iid, "pattern_id": None, "position": pos, "stage": l["stage"],
                              "statement": l["statement"], "tag": l["tag"], "evidence": {"source": l["evidence"],
                                                                                          "chain_available": ch["available"]}})
        sess.bulk_insert_mappings(CausalChainLink, links)
        sess.bulk_insert_mappings(ResolutionStrategy, [
            {"pattern_id": st["pattern_id"], "strategy_key": st["strategy_key"], "label": st["label"],
             "n_incidents": st["n_incidents"], "n_with_outcome": st["n_with_outcome"],
             "stats_supported": st["stats_supported"], "reopen_rate": st.get("reopen_rate"),
             "reopen_ci_low": st.get("reopen_ci_low"), "reopen_ci_high": st.get("reopen_ci_high"),
             "median_resolution_hours": st.get("median_resolution_hours"),
             "mean_reassignments": st.get("mean_reassignments"), "text_provenance": st["text_provenance"],
             "example_incident_ids": st["example_incident_ids"], "note": st["basis"]}
            for st in strategies])
        sess.bulk_insert_mappings(IncidentRelationship, edges)
        sess.execute(update(Incident).values(family_id=None))
        by_fam: dict[str, list[str]] = {}
        for iid, fid in engine.assign.items():
            by_fam.setdefault(fid, []).append(iid)
        for fid, members in by_fam.items():
            for i in range(0, len(members), 500):
                sess.execute(update(Incident).where(Incident.incident_id.in_(members[i:i + 500])).values(family_id=fid))
