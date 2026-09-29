"""Knowledge Base Evolution — documented batch process.

Processes every resolved live incident that has not yet been through the evolution loop
(quality re-score → index or manual review). Intended to run nightly, e.g. as a long-running
`--loop` process (interval from KB_BATCH_INTERVAL_S, default 86400 s = nightly) or from a scheduler.

Usage:
    python scripts/kb_evolution_batch.py            # run once
    python scripts/kb_evolution_batch.py --loop     # run forever at KB_BATCH_INTERVAL_S
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.database.session import init_db  # noqa: E402
from backend.knowledge.indexer import ensure_vector_index  # noqa: E402
from backend.services.platform import get_platform  # noqa: E402


def run_once() -> dict:
    p = get_platform()
    return p.kb_evolve()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    args = ap.parse_args()
    init_db()
    print(json.dumps({"vector_index": ensure_vector_index(get_platform().rt)}), flush=True)
    interval = int(os.environ.get("KB_BATCH_INTERVAL_S", "86400"))
    while True:
        res = run_once()
        print(json.dumps({"ran_at": res["ran_at"], "processed": res["processed"],
                          "results": [{k: r.get(k) for k in ("incident_id", "status", "family_id")} for r in res["results"]]}),
              flush=True)
        if not args.loop:
            break
        time.sleep(interval)
