"""Phase 4 (+ Phase 6 strategies) — fingerprints, families, causal chains, recurrence, graph, strategies.

Usage: python scripts/build_intelligence.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.intelligence.builder import build_all  # noqa: E402

if __name__ == "__main__":
    t = time.time()
    out = build_all()
    out["seconds"] = round(time.time() - t, 1)
    print(json.dumps(out, indent=2))
