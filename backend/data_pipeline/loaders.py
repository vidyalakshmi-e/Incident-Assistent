"""Source detection and loading.

The attached filenames do not describe their content (`incidents_text.csv` is the structured event
log, `incidents_structured.xlsx` is the text-rich file). Sources are therefore identified by
*content*, never by filename.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Columns that identify the structured ITSM event log (Source B).
STRUCTURED_MARKERS = {"CI_Cat", "CI_Subcat", "Impact", "Urgency", "Priority", "Closure_Code", "Open_Time"}
# Column-name fragments that suggest free text (Source A).
TEXT_MARKERS = ("description", "solution", "resolution", "details", "notes", "summary")


@dataclass
class DetectedSource:
    role: str  # "text_rich" (Source A) | "structured" (Source B)
    path: Path
    frame: pd.DataFrame
    reason: str


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path, low_memory=False)


def _text_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        if df[c].dtype != object:
            continue
        name_hit = any(m in c.lower() for m in TEXT_MARKERS)
        avg_words = df[c].dropna().astype(str).str.split().str.len().mean() or 0
        if name_hit and avg_words >= 2:
            cols.append(c)
    return cols


def detect_sources(raw_dir: Path) -> dict[str, DetectedSource]:
    found: dict[str, DetectedSource] = {}
    for path in sorted(raw_dir.iterdir()):
        if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
            continue
        df = read_any(path)
        structured_hits = STRUCTURED_MARKERS & set(df.columns)
        text_cols = _text_columns(df)
        if len(structured_hits) >= 5 and not text_cols:
            found["structured"] = DetectedSource(
                "structured", path, df,
                f"has structured ITSM columns {sorted(structured_hits)} and no free-text column",
            )
        elif text_cols:
            found["text_rich"] = DetectedSource(
                "text_rich", path, df, f"has free-text columns {text_cols}"
            )
    missing = {"structured", "text_rich"} - set(found)
    if missing:
        raise FileNotFoundError(f"Could not identify source(s) {missing} in {raw_dir}")
    return found
