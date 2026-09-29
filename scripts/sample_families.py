"""Print a reproducible sample of family members for MANUAL spot validation (docs/MANUAL_VALIDATION.md).

Usage: python scripts/sample_families.py [n_families] [n_members]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    n_fam = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n_mem = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    kb = pd.read_parquet(ROOT / "data/processed/kb_records.parquet").set_index("incident_id")
    pat = json.loads((ROOT / "data/processed/patterns.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(11)
    fams = sorted(pat["families"], key=lambda f: -f["size"])
    picks = [fams[i] for i in sorted(rng.choice(len(fams), size=min(n_fam, len(fams)), replace=False))]
    for f in picks:
        members = kb.loc[f["members"]]
        dom = members["gt_scenario"].value_counts()
        print(f"===== {f['family_id']} | {f['name']} | size {f['size']} | ground-truth mix {dict(dom.head(3))}")
        if f.get("cross_symptom"):
            print(f"      cross-symptom: {f['cross_symptom']['finding']}")
        for iid in rng.choice(f["members"], size=min(n_mem, len(f["members"])), replace=False):
            r = kb.loc[iid]
            print(f"  - {iid} [{r['gt_scenario']} / {r['gt_strategy']}] {str(r['description'])[:110]} || "
                  f"{str(r['resolution_notes'])[:100]}")
