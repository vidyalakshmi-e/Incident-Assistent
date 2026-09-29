"""LLM resolution synthesis + validation (skipped entirely in retrieval-only mode).

The LLM may only rephrase the top-ranked historical resolution into clear steps, citing the
incident IDs it used. Every synthesized step is then validated twice:
  1. deterministic grounding — embedding similarity to at least one cited historical note
  2. LLM validation — a second call judging SUPPORTED / UNSUPPORTED against the notes
Unsupported steps are flagged and kept visibly separate from the historical evidence.
"""
from __future__ import annotations

import re

import numpy as np

SYNTH_SYSTEM = ("You are an IT operations assistant. You only use the historical resolution notes provided. "
                "Never invent commands, systems or facts. Prefer non-destructive actions.")
GROUNDING_THRESHOLD = 0.45


def synthesize(llm, query: str, top: dict) -> dict | None:
    if llm is None or not llm.available or not top:
        return None
    notes = "\n".join(f"[{e['incident_id']}] {e['note']}" for e in top["evidence"][:5])
    prompt = (f"New incident: {query}\n\nHistorical resolution notes for the best-matching approach:\n{notes}\n\n"
              "Write 2-4 short numbered troubleshooting steps for the new incident based ONLY on these notes. "
              "End each step with the incident IDs it is based on in square brackets, e.g. [IM0001234].")
    out = llm.complete(prompt, system=SYNTH_SYSTEM, max_tokens=300, purpose="resolution_synthesis")
    if not out:
        return None
    steps = [re.sub(r"^\s*\d+[.)]\s*", "", l).strip() for l in out.splitlines() if re.match(r"^\s*\d+[.)]", l)]
    if not steps:
        steps = [out.strip()]
    return {"text": out, "steps": [{"text": s, "cited": re.findall(r"\[([A-Z]{2,4}-?\d{4,7})\]", s)} for s in steps],
            "model": llm.name, "kind": "LLM-generated synthesis"}


def validate(llm, embedder, synthesis: dict | None, top: dict) -> dict | None:
    if synthesis is None:
        return None
    notes = [e["note"] for e in top["evidence"][:5]]
    ids = [e["incident_id"] for e in top["evidence"][:5]]
    note_vecs = embedder.embed(notes)
    step_texts = [re.sub(r"\[[^\]]+\]", "", s["text"]).strip() for s in synthesis["steps"]]
    step_vecs = embedder.embed(step_texts)
    sims = step_vecs @ note_vecs.T
    checks = []
    for i, s in enumerate(synthesis["steps"]):
        j = int(np.argmax(sims[i]))
        bad_cites = [c for c in s["cited"] if c not in ids]
        checks.append({"step": s["text"], "best_support": ids[j], "grounding_similarity": round(float(sims[i, j]), 3),
                       "grounded": bool(sims[i, j] >= GROUNDING_THRESHOLD) and not bad_cites,
                       "invalid_citations": bad_cites})
    llm_verdicts = None
    if llm is not None and llm.available:
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(step_texts))
        ctx = "\n".join(f"[{i}] {n}" for i, n in zip(ids, notes))
        out = llm.complete(f"Historical notes:\n{ctx}\n\nProposed steps:\n{listing}\n\nFor each step answer on its own "
                           "line with the step number and SUPPORTED or UNSUPPORTED (is the step supported by the notes?).",
                           system="You are a strict fact checker.", max_tokens=120, purpose="llm_validation")
        if out:
            llm_verdicts = {int(m.group(1)): m.group(2).upper() for m in re.finditer(r"(\d+)\D{0,5}(SUPPORTED|UNSUPPORTED)", out, re.I)}
            for i, c in enumerate(checks):
                c["llm_verdict"] = llm_verdicts.get(i + 1, "NO VERDICT")
    unsupported = [c for c in checks if not c["grounded"] or c.get("llm_verdict") == "UNSUPPORTED"]
    return {"checks": checks, "all_grounded": not unsupported, "unsupported_steps": len(unsupported),
            "method": "embedding grounding (threshold 0.45) + citation check" + (" + LLM verdicts" if llm_verdicts else "")}
