"""LLM guidance for troubleshooting: make historical evidence fit THIS incident.

The ranking (rag/resolution.py) is deliberately mechanical: it picks the resolution notes of the most similar
historical incidents. That is right for *which* approach has the most evidence, but the note itself is written
about somebody else's ticket. It can read as a status line ("The vendor hotfix was deployed to address this
issue") or name a fix that has no connection to what the engineer just reported. Two things the LLM does here:

  1. guide_steps   — judge each candidate step against the reported incident: keep it or drop it, and if
                     kept, restate it as an instruction the engineer can act on now, plus the question to
                     answer once they have tried it ("what happened when you tried it?").
  2. phrase_question — word the clarifying question for this incident instead of a generic one.

What the LLM may NOT do: change the confidence (computed from evidence in rag/resolution.py), invent a step
that is not in the historical note, or pick which clarification field is asked. A restated step must stay
semantically close to its note (embedding check); otherwise the original wording is kept. With no LLM, every
function returns None and callers keep the mechanical behaviour, labelled as retrieval-only mode.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

GUIDE_SYSTEM = (
    "You are a senior IT support engineer coaching a colleague through an incident. You are given the incident "
    "as reported and candidate steps taken from OTHER, older incidents' resolution notes. Use only what the notes "
    "say; never invent commands, tools, systems or settings that are not in the note or the report."
)
QUESTION_SYSTEM = (
    "You are a senior IT support engineer. Ask ONE short, plain-language question that helps narrow down an "
    "incident. Refer to what the person actually reported; do not repeat generic wording."
)
# A restated step must stay this close (cosine, MiniLM) to the historical note it came from.
ADAPTED_MIN_SIMILARITY = 0.30
MAX_NOTE_CHARS = 420
CHUNK = 3  # candidates per LLM call: three answers fit the gateway's 500-token reply cap; chunks run in parallel


def _clip(s: str | None, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 3].rstrip() + "..."


def _clean_line(v, limit: int) -> str | None:
    if not isinstance(v, str):
        return None
    v = " ".join(v.split()).strip(" \"'")
    return _clip(v, limit) if v else None


def _judge_chunk(llm, incident_text: str, chunk: list[dict], failed_steps: list[str]) -> dict[int, dict]:
    """One LLM call for up to CHUNK candidates. Returns {1-based position in the chunk: the model's object}."""
    lines = [f"{i}. NOTE: {_clip(c.get('step') or c.get('action'), MAX_NOTE_CHARS)}" for i, c in enumerate(chunk, 1)]
    tried = "\n".join(f"- {_clip(s, 160)}" for s in failed_steps[:5]) or "- nothing yet"
    prompt = (
        f"INCIDENT AS REPORTED:\n{_clip(incident_text, 600)}\n\n"
        f"ALREADY TRIED AND FAILED:\n{tried}\n\n"
        "CANDIDATE STEPS (from older, similar incidents):\n" + "\n".join(lines) + "\n\n"
        "For every candidate return an object with these keys:\n"
        '  "id": the candidate number\n'
        '  "relevant": true only if doing this would plausibly help with the symptoms in THIS report. '
        'Say false for notes that only state that someone else already did something ("vendor hotfix was '
        'deployed", "issue resolved"), that concern a different system or symptom, or that give nothing an '
        "engineer can do.\n"
        '  "reason": under 12 words, why it is or is not relevant to this report\n'
        '  "action": if relevant, ONE imperative sentence (under 25 words) telling the engineer what to do now, '
        'worded for this incident and based only on the note (e.g. turn "vendor hotfix was deployed" into '
        '"Check whether the vendor has released a hotfix for the slow component and apply it"); else ""\n'
        '  "observe": if relevant, ONE question (under 16 words) asking what they saw after doing it, specific '
        'to this action (e.g. "After applying it, did opening a record still take a long time?"); else ""\n'
        '  "outcomes": if relevant, exactly two short first-person sentences (under 14 words each) the engineer '
        "might report, the first if it helped, the second if it did not; else []\n"
        'Return {"steps": [ ... ]} with one object per candidate, in order.'
    )
    data = llm.complete_json(prompt, system=GUIDE_SYSTEM, max_tokens=500, purpose="step_guidance")
    items = data.get("steps") if isinstance(data, dict) else data
    out: dict[int, dict] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            try:
                out[int(it.get("id"))] = it
            except (TypeError, ValueError):
                continue
    return out


def guide_steps(llm, incident_text: str, candidates: list[dict], failed_steps: list[str] | None = None,
                embedder=None) -> dict[str, dict] | None:
    """Judge and restate candidate steps. Returns {strategy_key: guidance} for every candidate the model answered
    for, or None when the LLM is unavailable / unusable (callers then keep the historical wording).

    guidance = {relevant, reason, action, adapted, observe, outcomes[2], model}
    """
    if llm is None or not llm.available or not candidates:
        return None
    chunks = [candidates[i:i + CHUNK] for i in range(0, len(candidates), CHUNK)]
    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        answered = list(pool.map(lambda ch: _judge_chunk(llm, incident_text, ch, list(failed_steps or [])), chunks))
    # re-key every answer by its position in the full candidate list (1-based)
    by_id: dict[int, dict] = {}
    for n, got in enumerate(answered):
        for pos, it in got.items():
            if 1 <= pos <= len(chunks[n]):
                by_id[n * CHUNK + pos] = it
    if not by_id:
        return None

    # keep restated wording only when it still says what the note says
    adapted_ok: dict[int, bool] = {}
    if embedder is not None:
        pairs = [(i, _clean_line(by_id[i].get("action"), 220), candidates[i - 1]) for i in by_id
                 if by_id[i].get("relevant") is True]
        pairs = [(i, a, c) for i, a, c in pairs if a]
        if pairs:
            try:
                a_vec = embedder.embed([a for _, a, _ in pairs])
                n_vec = embedder.embed([_clip(c.get("step") or c.get("action"), MAX_NOTE_CHARS) for _, _, c in pairs])
                for (i, _, _), va, vn in zip(pairs, a_vec, n_vec):
                    adapted_ok[i] = float(va @ vn) >= ADAPTED_MIN_SIMILARITY
            except Exception as exc:  # noqa: BLE001 — an embedding hiccup must not lose the guidance
                log.warning("grounding check skipped: %s", exc)

    out: dict[str, dict] = {}
    for i, c in enumerate(candidates, 1):
        it = by_id.get(i)
        if it is None:
            continue  # the model skipped it: leave the candidate untouched rather than guess
        relevant = it.get("relevant") is True
        action = _clean_line(it.get("action"), 220) if relevant else None
        grounded = adapted_ok.get(i, True) if embedder is not None else True
        outcomes = [o for o in (_clean_line(x, 140) for x in (it.get("outcomes") or [])[:2]) if o]
        out[c["strategy_key"]] = {
            "relevant": relevant,
            "reason": _clean_line(it.get("reason"), 140),
            "action": action if (action and grounded) else None,
            "adapted": bool(action and grounded),
            "observe": _clean_line(it.get("observe"), 160) if relevant else None,
            "outcomes": outcomes if len(outcomes) == 2 else [],
            "model": llm.name,
        }
    return out or None


def apply_guidance(candidates: list[dict], guidance: dict[str, dict] | None) -> tuple[list[dict], list[dict]]:
    """Return (kept, filtered_out). Kept candidates carry `guidance`; when the step was restated, `action` becomes
    the restated text and `historical_action` keeps the original so the UI can show both."""
    if not guidance:
        return candidates, []
    kept, dropped = [], []
    for c in candidates:
        g = guidance.get(c["strategy_key"])
        if g is None:
            kept.append(c)
            continue
        if not g["relevant"]:
            dropped.append({"strategy_key": c["strategy_key"], "action": c["action"], "reason": g.get("reason"),
                            "confidence": c.get("confidence")})
            continue
        item = {**c, "guidance": g}
        if g["adapted"]:
            item["historical_action"] = c["action"]
            item["action"] = g["action"]
        kept.append(item)
    return kept, dropped


def apply_to_ranking(ranking: dict, guidance: dict[str, dict] | None) -> dict:
    """Filter/restate a ranking's top + alternatives with the LLM's judgement."""
    if not guidance:
        return ranking
    cands = ([ranking["top"]] if ranking["top"] else []) + list(ranking["alternatives"])
    kept, dropped = apply_guidance(cands, guidance)
    out = dict(ranking)
    out["top"], out["alternatives"] = (kept[0] if kept else None), kept[1:]
    out["filtered_as_irrelevant"] = dropped
    return out


def phrase_question(llm, incident_text: str, field: str, question: str, options: list[str],
                    tried: list[str] | None = None) -> dict | None:
    """Reword a clarifying question for this incident. The field being asked and the option VALUES stay as the
    policy chose them (they map to fingerprint values); only the wording changes. Returns
    {question, options (same order/count), why} or None."""
    if llm is None or not llm.available:
        return None
    tried_txt = "; ".join(_clip(t, 100) for t in (tried or [])[:3]) or "nothing yet"
    opts = "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1))
    prompt = (
        f"INCIDENT AS REPORTED: {_clip(incident_text, 500)}\n"
        f"ALREADY TRIED: {tried_txt}\n\n"
        f'We need to find out this one thing: "{question}" (field: {field.replace("_", " ")}).\n'
        f"The person will choose from these answers:\n{opts}\n\n"
        "Return JSON with:\n"
        '  "question": that question rewritten for this incident, one sentence, under 30 words, ending with "?"\n'
        '  "options": the same answers reworded to fit your question, SAME number and SAME order, each under 8 words\n'
        '  "why": under 20 words on how the answer will change what we suggest next'
    )
    data = llm.complete_json(prompt, system=QUESTION_SYSTEM, max_tokens=300, purpose="clarifying_question")
    if not isinstance(data, dict):
        return None
    q = _clean_line(data.get("question"), 240)
    if not q or not q.endswith("?"):
        return None
    new_opts = data.get("options")
    labels = [_clean_line(o, 80) for o in new_opts] if isinstance(new_opts, list) else []
    if len(labels) != len(options) or not all(labels) or len(set(labels)) != len(labels):
        labels = list(options)  # wording of the choices is optional; the question is what matters
    return {"question": q, "options": labels, "why": _clean_line(data.get("why"), 200)}
