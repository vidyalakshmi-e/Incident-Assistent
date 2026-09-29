"""Run the whole offline pipeline in order (each step in a fresh process).

    1. build_dataset.py      Phase 1  unified dataset + conditioned synthetic text (cached LLM text reused)
    2. build_index.py        Phase 2  Quality Manager, embeddings, ChromaDB, SQL
    3. build_intelligence.py Phase 4  fingerprints, families, causal chains, recurrence, graph, strategies
    4. train_models.py       Phase 7  triage models (resolution time, fix accuracy, text classifiers)
    5. calibrate.py          Phase 5  cross-encoder calibration + novelty threshold (validation split)
    6. run_evaluation.py     Phase 9  all metrics (optional: --with-eval)

Usage: python scripts/build_all.py [--with-eval] [--keep-db]
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script: str, *args: str) -> None:
    t = time.time()
    print(f"\n=== {script} {' '.join(args)}", flush=True)
    r = subprocess.run([sys.executable, str(HERE / script), *args])
    if r.returncode != 0:
        sys.exit(f"{script} failed with exit code {r.returncode}")
    print(f"=== {script} done in {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    run("build_dataset.py")
    run("build_index.py", *([] if "--keep-db" in sys.argv else ["--fresh"]))
    run("build_intelligence.py")
    run("train_models.py")
    run("calibrate.py", "--rule-queries") if not (HERE.parent / "data/evaluation/eval_queries.jsonl").exists() \
        and "--llm-queries" not in sys.argv else run("calibrate.py")
    if "--with-eval" in sys.argv:
        run("run_evaluation.py")
