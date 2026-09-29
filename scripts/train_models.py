"""Train triage models (resolution time, fix accuracy, text classifiers) and write test metrics.

Usage: python scripts/train_models.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from backend.config.settings import get_settings  # noqa: E402
from backend.evaluation.train_models import train_all  # noqa: E402
from backend.services.triage import save_models  # noqa: E402

if __name__ == "__main__":
    s = get_settings()
    unified = pd.read_parquet(s.processed_dir / "incidents_unified.parquet")
    kb = pd.read_parquet(s.processed_dir / "kb_records.parquet")
    bundle = train_all(unified, kb)
    save_models(bundle, s)
    out = {"resolution_time": bundle["resolution_time"]["test_metrics"],
           "fix_accuracy": bundle["fix_accuracy"]["test_metrics"],
           "text_classifiers": {k: {m: v[m] for m in ("accuracy", "macro_f1", "weighted_f1",
                                                      "majority_class_baseline_accuracy", "n_test")}
                                for k, v in bundle["text_classifier_metrics"].items()}}
    print(json.dumps(out, indent=2))
