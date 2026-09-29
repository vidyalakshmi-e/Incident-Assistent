"""Phase 3 checkpoint — one full hybrid retrieval response.

Usage: python scripts/demo_retrieval.py "the system feels slow and basic things take forever"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("USE_TF", "0")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.schemas.retrieval import RetrievalFilters  # noqa: E402
from backend.services.runtime import get_runtime  # noqa: E402

DEFAULT = ("The application is becoming slower and sometimes freezes when users try to open records. "
           "Restarting fixes it temporarily.")


def main() -> None:
    q = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    filters = RetrievalFilters.model_validate_json(sys.argv[2]) if len(sys.argv) > 2 else None
    rt = get_runtime()
    rt.retriever.search("warm-up")  # load models before timing
    resp = rt.retriever.search(q, filters=filters, top_k=5)
    out = resp.model_dump(mode="json")
    for r in out["results"]:
        r["description"] = (r["description"] or "")[:160]
        r["resolution_notes"] = (r["resolution_notes"] or "")[:160]
        r["metadata"] = {k: r["metadata"][k] for k in ("category", "ci_name", "priority", "closure_code", "source")}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
