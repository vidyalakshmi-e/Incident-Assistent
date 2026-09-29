"""Step 1: profile the real files before any pipeline decision is made."""
from __future__ import annotations

from typing import Any

import pandas as pd

# Field list the prompt *expects* for each source. Compared against what actually exists.
EXPECTED_TEXT_FIELDS = ["description", "resolution_notes", "Incident Details", "Description", "Solution"]
EXPECTED_STRUCTURED_FIELDS = [
    "CI_Cat", "CI_Subcat", "Impact", "Urgency", "Priority", "Status", "Reopen_Time",
    "No_of_Reassignments", "Closure_Code", "Open_Time", "Resolved_Time",
    "No_of_Related_Incidents", "Related_Change",
]


def profile_frame(df: pd.DataFrame, n_samples: int = 5) -> dict[str, Any]:
    cols = []
    for c in df.columns:
        s = df[c]
        cols.append({
            "column": c,
            "dtype": str(s.dtype),
            "nulls": int(s.isna().sum()),
            "null_pct": round(float(s.isna().mean()) * 100, 2),
            "unique": int(s.nunique(dropna=True)),
            "top_values": {str(k): int(v) for k, v in s.value_counts(dropna=False).head(6).items()},
        })
    return {
        "rows": int(len(df)),
        "columns": cols,
        "samples": df.head(n_samples).astype(str).to_dict(orient="records"),
    }


def compare_expected(df: pd.DataFrame, expected: list[str]) -> dict[str, list[str]]:
    present = set(df.columns)
    return {
        "expected_and_present": [c for c in expected if c in present],
        "expected_but_missing": [c for c in expected if c not in present],
        "present_but_not_expected": [c for c in df.columns if c not in expected],
    }
