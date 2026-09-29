"""Produce the phase checkpoint outputs requested by the build plan (docs/checkpoints/*.json).

Runs against an isolated SQLite database and an isolated ChromaDB collection, so the demo state
(sessions, KB additions) does not leak into the shipped artefacts.

Usage: python scripts/demo_checkpoints.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("USE_TF", "0")
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'evaluation' / 'checkpoints.db').as_posix()}"
os.environ["CHROMA_COLLECTION"] = "incident_kb_checkpoints"
os.environ["LLM_API_KEY"] = ""  # the Phase 7 fallback demo needs retrieval-only mode
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from backend.database.session import reset_db  # noqa: E402
from backend.knowledge.indexer import ensure_vector_index  # noqa: E402
from backend.schemas.api import FeedbackRequest, SimulateRequest, TroubleshootRequest as TR  # noqa: E402
from backend.services.platform import get_platform  # noqa: E402

OUT = ROOT / "docs" / "checkpoints"
DEMO = ("The application is becoming slower and sometimes freezes when users try to open records. "
        "Restarting fixes it temporarily.")


def save(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    print(f"wrote docs/checkpoints/{name}.json")


def main() -> None:
    reset_db()
    p = get_platform()
    rt = p.rt
    ensure_vector_index(rt)
    proc = rt.s.processed_dir

    # ---------------- Phase 1
    u = pd.read_parquet(proc / "incidents_unified.parquet")
    rep = json.loads((proc / "dataset_report.json").read_text(encoding="utf-8"))
    cols = ["incident_id", "source", "category", "category_source", "ci_subcategory", "priority", "priority_source",
            "closure_code", "open_time", "resolution_hours", "resolution_hours_source", "title", "description",
            "description_source", "resolution_notes", "resolution_notes_source", "text_generator"]
    samples = pd.concat([u[u["source"] == "A_text_rich"].head(2), u[(u["source"] == "B_event_log") & u["in_kb"]].head(2),
                         u[(u["source"] == "B_event_log") & ~u["in_kb"]].head(1)])[cols]
    save("phase1_dataset", {"unified_schema_columns": list(u.columns), "sample_rows": samples.to_dict(orient="records"),
                            "original_row_count": rep["original_row_count"],
                            "knowledge_base": {k: rep["knowledge_base"][k] for k in ("incidents", "text_field_ratio", "text_generators")},
                            "cell_proportions": rep["cell_proportions_all_rows"]})

    # ---------------- Phase 2
    kb = rt.store.records
    picks = pd.concat([kb[kb["quality_tier"] == t].head(2) for t in ("high", "medium", "low")])
    r = rt.retriever.search("database queries time out during peak hours", top_k=3)
    save("phase2_quality_and_retrieval", {
        "quality_samples": picks[["incident_id", "resolution_notes", "quality_score", "quality_tier", "quality_flags",
                                  "quality_components", "influence_weight"]].to_dict(orient="records"),
        "test_retrieval": [{"incident_id": x.incident_id, "title": x.title, "relevance": x.scores.relevance_confidence,
                            "why": x.why_retrieved.summary} for x in r.results]})

    # ---------------- Phase 3
    full = p.search("the system feels slow and basic things take forever", top_k=3)
    save("phase3_retrieval_response", {k: full[k] for k in ("query_understanding", "results", "mode", "timings_ms")})

    # ---------------- Phase 4
    fam_id = rt.patterns.assign[r.results[0].incident_id]
    fam = p.pattern(fam_id)
    ex = next(c for c in (p.agents.pattern_agent.causal_chain(m) for m in rt.patterns.families[fam_id].members)
              if c and c["available"] and len(c["links"]) >= 5)
    fps = {i: rt.patterns.fingerprints[i] for i in list(rt.patterns.fingerprints)[:3]}
    save("phase4_patterns", {"sample_fingerprints": fps,
                             "family": {k: fam[k] for k in ("family_id", "name", "size", "signature", "cross_symptom",
                                                             "causal_chain", "recurrence", "strategies")},
                             "incident_causal_chain": ex})

    # ---------------- Phase 5
    nov = json.loads((rt.s.evaluation_dir / "novelty_results.json").read_text(encoding="utf-8"))["novelty"]
    save("phase5_novelty", {k: nov[k] for k in ("threshold_p_known", "model_weights", "validation", "test",
                                                 "baseline_single_feature")})

    # ---------------- Phase 6: troubleshooting trace + clarification before escalation
    s = p.troubleshoot(TR(action="start", text=DEMO))["session"]
    trace = [s]
    for _ in range(6):
        if s["status"] == "awaiting_clarification":
            s = p.troubleshoot(TR(action="clarify", session_id=s["session_id"],
                                  answer="yes, after a deployment / release"))["session"]
        elif s["status"] == "active":
            s = p.troubleshoot(TR(action="respond", session_id=s["session_id"],
                                  attempt_id=s["current_step"]["attempt_id"], response="FAILED",
                                  notes="no change"))["session"]
        else:
            break
        trace.append(s)
    save("phase6_troubleshooting_trace", {
        "steps": [{"status": x["status"], "round": x["round"],
                   "current_step": (x["current_step"] or {}).get("action"),
                   "confidence": (x["current_step"] or {}).get("confidence"),
                   "clarification": (x["clarification"] or {}).get("question")} for x in trace],
        "attempt_log": s["attempts"], "clarifications": s["clarifications"], "events": s["events"]})
    vague = p.troubleshoot(TR(action="start", text="the system is slow"))["session"]
    save("phase6_clarification_example", {"query": "the system is slow", "status": vague["status"],
                                          "clarification": vague["clarification"], "novelty": vague["novelty"]})

    # ---------------- Phase 7: escalation packet, correlation alert, retrieval-only fallback
    save("phase7_escalation_packet", s.get("escalation"))
    corr = p.simulate(SimulateRequest(preset="db-outage-burst", reset=True))
    noise = p.simulate(SimulateRequest(preset="unrelated-noise", reset=True))
    save("phase7_correlation", {"burst_alerts": corr["alerts"], "burst_events": [x["event"] for x in corr["ingested"]],
                                "noise_alerts": noise["alerts"]})
    a = p.analyze(DEMO)
    save("phase7_retrieval_only_mode", {"mode_labels": a["mode_labels"], "llm_synthesis": a["llm_synthesis"],
                                        "top_resolution": a["top_resolution"], "health_llm": p.health()["llm"],
                                        "agent_messages": a["agent_messages"]})

    # ---------------- Phase 8: evidence chain + KB update cycle
    save("phase8_evidence_chain", a["evidence_chain"])
    text = "Nightly payroll interface job aborted because the upstream bank file arrived with a malformed header"
    s2 = p.troubleshoot(TR(action="start", text=text))["session"]
    if s2["status"] == "awaiting_clarification":
        s2 = p.troubleshoot(TR(action="clarify", session_id=s2["session_id"], declined=True))["session"]
    before = [x["incident_id"] for x in p.search(text, top_k=5)["results"]]
    s2 = p.troubleshoot(TR(action="respond", session_id=s2["session_id"], attempt_id=s2["current_step"]["attempt_id"],
                           response="WORKED", notes="Upstream team redelivered the file with a corrected header; job rerun, "
                                                    "record counts reconciled."))["session"]
    pm = p.postmortem(s2["incident_id"], feed_to_kb=False)
    fb = p.feedback(FeedbackRequest(incident_id=s2["incident_id"], session_id=s2["session_id"], helpful=True,
                                    root_cause_correct=True, pattern_correct=True, troubleshooting_resolved=True))
    p._last_refresh = 0
    after = [x["incident_id"] for x in p.search(text, top_k=5)["results"]]
    save("phase8_kb_evolution_cycle", {"incident_id": s2["incident_id"], "retrieved_before": before,
                                       "postmortem": pm["postmortem"], "feedback_result": fb,
                                       "retrieved_after": after, "evolution_view": p.kb_evolution_view()})
    try:  # drop the isolated collection again
        rt.vectors._connect()
        rt.vectors._client.delete_collection("incident_kb_checkpoints")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
