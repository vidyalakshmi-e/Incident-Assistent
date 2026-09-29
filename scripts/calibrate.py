"""Phase 5 — build the labelled query set, calibrate the cross-encoder and the novelty threshold.

Usage: python scripts/calibrate.py [--rule-queries]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.evaluation.calibration import calibrate  # noqa: E402
from backend.evaluation.query_generator import build_eval_set  # noqa: E402
from backend.services.runtime import get_runtime  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rule-queries", action="store_true", help="use the rule paraphraser instead of the local LLM")
    ap.add_argument("--per-family", type=int, default=10)
    args = ap.parse_args()
    rt = get_runtime()
    s = rt.s
    out = s.evaluation_dir / "eval_queries.jsonl"
    gen = None
    if not out.exists() and not args.rule_queries:
        try:
            from backend.data_pipeline.llm_verbalizer import LocalHFBatchGenerator
            gen = LocalHFBatchGenerator(os.environ.get("EVAL_QUERY_LLM", "Qwen/Qwen2.5-3B-Instruct"))
        except Exception as exc:  # noqa: BLE001
            print(f"LLM query generation unavailable ({exc}); using rule paraphraser")
    df = build_eval_set(rt.store.records, s.evaluation_dir / "novel_probes.jsonl", out,
                        per_family=args.per_family, llm_generator=gen)
    del gen
    res = calibrate(rt, df, s.evaluation_dir / "calibration.json")
    (s.evaluation_dir / "novelty_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    show = {"platt": res["platt"], "threshold_p_known": res["novelty"]["threshold_p_known"],
            "weights": res["novelty"]["model_weights"], "validation": res["novelty"]["validation"],
            "test": res["novelty"]["test"], "test_by_style": res["novelty"]["test_by_style"],
            "baseline_single_feature_test": res["novelty"]["baseline_single_feature"]["test"],
            "query_set": {f"{a}/{b}": int(n) for (a, b), n in df.groupby(["split", "label"]).size().items()}}
    print(json.dumps(show, indent=2, default=str))


if __name__ == "__main__":
    main()
