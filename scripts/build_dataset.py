"""Phase 1 — build the unified, provenance-tagged dataset.

Usage:
    python scripts/build_dataset.py                    # reuse cached LLM text if present, else template grammar
    python scripts/build_dataset.py --generator llm --llm-model Qwen/Qwen2.5-3B-Instruct
    python scripts/build_dataset.py --generator template
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.data_pipeline.build import run  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--generator", choices=["auto", "llm", "template"], default="auto")
    ap.add_argument("--llm-model", default=None, help="HF model id for local LLM generation")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--rows", type=int, default=3000)
    args = ap.parse_args()
    model = args.llm_model or ("Qwen/Qwen2.5-3B-Instruct" if args.generator == "llm" else None)
    report = run(generator=args.generator, llm_model=model, seed=args.seed, target_rows=args.rows)
    print(json.dumps({k: report[k] for k in ("original_row_count", "augmented_synthetic_rows", "knowledge_base")}, indent=2))


if __name__ == "__main__":
    main()
