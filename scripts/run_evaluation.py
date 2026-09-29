"""Phase 9 — run the full evaluation suite and write data/evaluation/evaluation_results.json.

Usage:
    python scripts/run_evaluation.py                      # retrieval-only mode (no LLM needed)
    python scripts/run_evaluation.py --llm-local 40       # + LLM-mode RAG metrics with a local HF model
    python scripts/run_evaluation.py --quick              # small subsets (used by the reproducibility test)

Troubleshooting / escalation sessions created during evaluation go to a separate SQLite database
(data/evaluation/eval.db) so the demo database is not polluted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("USE_TF", "0")
os.environ["DATABASE_URL"] = f"sqlite:///{(ROOT / 'data' / 'evaluation' / 'eval.db').as_posix()}"
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from backend.database.session import init_db, session_scope  # noqa: E402
from backend.evaluation import suite  # noqa: E402
from backend.models.entities import EvaluationResult  # noqa: E402
from backend.rag.strategy import StrategyIndex  # noqa: E402
from backend.services.runtime import get_runtime  # noqa: E402


def dataset_fingerprint(proc: Path) -> str:
    h = hashlib.sha256()
    for name in ("kb_records.parquet", "patterns.json", "strategies.json"):
        h.update((proc / name).read_bytes())
    return h.hexdigest()[:16]


def flatten(prefix: str, obj, out: list) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append((prefix, float(obj)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-local", type=int, default=0, help="also evaluate LLM synthesis on N queries with a local HF model")
    ap.add_argument("--llm-model", default="Qwen/Qwen2.5-3B-Instruct")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    init_db()
    rt = get_runtime()
    s = rt.s
    sidx = StrategyIndex.load(s.processed_dir)
    queries = pd.read_json(s.evaluation_dir / "eval_queries.jsonl", lines=True)
    if args.quick:
        queries = pd.concat([g.head(12) for _, g in queries.groupby(["split", "label"])])
    t0 = time.time()
    res: dict = {"run_id": f"EVAL-{uuid.uuid4().hex[:8]}", "created_at": datetime.utcnow().isoformat(),
                 "dataset_fingerprint": dataset_fingerprint(s.processed_dir), "seed": s.random_seed,
                 "query_set": {f"{a}/{b}": int(n) for (a, b), n in queries.groupby(["split", "label"]).size().items()},
                 "query_generator": queries["generator"].value_counts().to_dict(),
                 "components": {"embedder": rt.embedder.name, "reranker": rt.reranker.name, "llm": rt.llm.status()}}
    timings = {}

    def step(name, fn, *a, **kw):
        t = time.time()
        print(f"[eval] {name} ...", flush=True)
        res[name] = fn(*a, **kw)
        timings[name] = round(time.time() - t, 1)

    step("retrieval", suite.eval_retrieval, rt, queries)
    step("rag", suite.eval_rag, rt, queries, sidx)
    if args.llm_local:
        from backend.config.settings import Settings
        from backend.rag.llm import LLMClient

        llm = LLMClient(Settings(llm_provider="local", llm_model=args.llm_model), read_cache=False)
        step("rag_llm_mode", suite.eval_rag_llm, rt, queries, sidx, llm, args.llm_local)
    else:
        res["rag_llm_mode"] = {"status": "not run (pass --llm-local N, or configure LLM_API_KEY)"}
    model_metrics = json.loads((s.evaluation_dir / "model_metrics.json").read_text(encoding="utf-8"))
    res["classification"] = model_metrics.get("text_classifiers")
    res["resolution_time"] = model_metrics.get("resolution_time")
    res["fix_accuracy"] = model_metrics.get("fix_accuracy")
    if not args.quick:
        step("patterns", suite.eval_patterns, rt)
    step("causal_chains", suite.eval_causal_chains, rt)
    step("quality_manager", suite.eval_quality_manager, rt)
    step("novelty", suite.eval_novelty, rt)
    step("troubleshooting", suite.eval_troubleshooting, rt, queries, sidx)
    step("correlation", suite.eval_correlation, rt, queries)
    step("evidence_chain", suite.eval_evidence_chain, rt, queries, sidx)
    import torch

    device = "cuda:" + torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    res["latency"] = suite.eval_latency(res["retrieval"].pop("timings"), res["rag"].pop("stage_timings"),
                                        (res.get("rag_llm_mode") or {}).get("latency_ms"), device)
    res["eval_step_seconds"] = timings
    res["total_seconds"] = round(time.time() - t0, 1)

    out = Path(args.out) if args.out else s.evaluation_dir / ("evaluation_results_quick.json" if args.quick
                                                              else "evaluation_results.json")
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    if not args.quick:
        # the calibrated correlation threshold is used by the live correlator
        cal_path = s.evaluation_dir / "calibration.json"
        cal = json.loads(cal_path.read_text(encoding="utf-8"))
        cal["correlation_similarity"] = {"value": res["correlation"]["selected_similarity_threshold"],
                                         "fitted_on": "validation streams (see evaluation_results.json → correlation)"}
        cal_path.write_text(json.dumps(cal, indent=2), encoding="utf-8")
        rows: list = []
        flatten("", {k: v for k, v in res.items() if k not in ("components",)}, rows)
        main_db = f"sqlite:///{(ROOT / 'data' / 'processed' / 'incidents.db').as_posix()}"
        init_db(main_db)
        with session_scope(main_db) as sess:
            for metric, value in rows:
                sess.add(EvaluationResult(run_id=res["run_id"], suite=metric.split(".")[0], metric=metric, value=value))
    print(f"[eval] wrote {out} in {res['total_seconds']}s")


if __name__ == "__main__":
    main()
