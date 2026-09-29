"""Strategic chunking: one incident = one chunk.

An incident is the natural retrieval unit; splitting it on a fixed character/token window would
separate symptoms from their resolution and produce fragments that no engineer would search for.
Each chunk is enriched with a structured metadata header (category, derived severity, impact
scope, CI group) that is embedded together with the text. Only unusually long free text is split,
and only on sentence boundaries — never on a fixed window.
"""
from __future__ import annotations

import re

import pandas as pd

LONG_TEXT_WORDS = 300  # descriptions longer than this are split on sentence boundaries
MAX_CHUNK_WORDS = 200

_SENT = re.compile(r"(?<=[.!?])\s+")


def metadata_header(row: pd.Series) -> str:
    parts = [f"Category: {row['category']}"]
    if row.get("ci_subcategory") and row["ci_subcategory"] != "Unknown":
        parts.append(f"CI type: {row['ci_subcategory']}")
    if row.get("severity") and row["severity"] != "Unknown":
        parts.append(f"Severity: {row['severity']}")
    if row.get("impact_scope") and row["impact_scope"] != "Unknown":
        parts.append(f"Impact scope: {row['impact_scope']}")
    return " | ".join(parts)


def split_sentences(text: str, max_words: int = MAX_CHUNK_WORDS) -> list[str]:
    sents = [s for s in _SENT.split(text.strip()) if s]
    chunks, cur, n = [], [], 0
    for s in sents:
        w = len(s.split())
        if cur and n + w > max_words:
            chunks.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks


def build_documents(kb: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in kb.iterrows():
        header = metadata_header(r)
        desc = str(r["description"])
        desc_parts = split_sentences(desc) if len(desc.split()) > LONG_TEXT_WORDS else [desc]
        for i, part in enumerate(desc_parts):
            text = f"{header}\n{r['title']}. {part}\nResolution: {r['resolution_notes']}"
            rows.append({
                "chunk_id": f"{r['incident_id']}#{i}",
                "incident_id": r["incident_id"],
                "chunk_index": i,
                "n_chunks": len(desc_parts),
                "text": text,
                "symptom_text": f"{r['title']}. {part}",
            })
    return pd.DataFrame(rows)
