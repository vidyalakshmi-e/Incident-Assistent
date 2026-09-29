"""Per-query evaluation: how well can the knowledge base answer THIS query?

A relevant query (clear symptom, known pattern) scores high; an unrelated, gibberish or unseen query
scores low. The score is the unweighted mean of four signals the pipeline already computes, each in [0, 1]:

  relevance  best calibrated P(relevant) among the retrieved incidents (cross-encoder, Platt-calibrated)
  known      P(known pattern) from the calibrated novelty model
  pattern    match strength of the best pattern family (0 when no family matched)
  fix        confidence of the top ranked resolution (0 when none is recommended)

A signal that cannot be computed (degraded retrieval mode) is left out of the mean and labelled.
GOOD_MIN / FAIR_MIN are display bands for reading the score, not fitted thresholds. A query the novelty
model calls novel is always Poor, so the grade never contradicts the verdict shown next to it.
"""
from __future__ import annotations

GOOD_MIN = 0.70
FAIR_MIN = 0.40

LABELS = {"good": "Good", "fair": "Fair", "poor": "Poor"}


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def evaluate_query(bundle, top: dict | None) -> dict:
    """Evaluate one analysed query. `bundle` is an AnalysisBundle, `top` the ranked top resolution (or None)."""
    results = bundle.retrieval.results
    nov = bundle.novelty
    novel = nov.get("is_novel") is True
    fam = bundle.families[0] if bundle.families else None
    qu = bundle.qu
    if novel:  # a novel incident never gets a historical fix forced onto it
        top = None

    rels = [r.scores.relevance_confidence for r in results if r.scores.relevance_confidence is not None]
    relevance = max(rels) if rels else None
    known = nov.get("known_probability")
    pattern = float(fam["match_strength"]) if fam else 0.0
    fix = float(top["confidence"]) if top and top.get("confidence") is not None else 0.0

    components = [
        {"key": "relevance", "label": "Retrieval relevance", "value": relevance,
         "detail": (f"best of {len(results)} retrieved incidents; calibrated P(relevant)" if relevance is not None
                    else "not available: retrieval was not reranked")},
        {"key": "known", "label": "Known pattern", "value": known,
         "detail": (f"P(known) against the validated threshold {nov['threshold']:.2f}" if known is not None
                    else "not available: novelty model needs reranked hybrid retrieval")},
        {"key": "pattern", "label": "Pattern match", "value": pattern,
         "detail": (f"family {fam['family_id']}, match strength" if fam else "no pattern family matched")},
        {"key": "fix", "label": "Fix confidence", "value": fix,
         "detail": ("confidence of the top ranked resolution" if top
                    else "no historical fix is recommended" + (" for a novel incident" if novel else ""))},
    ]
    used = [c["value"] for c in components if c["value"] is not None]
    score = round(sum(used) / len(used), 3) if used else 0.0

    if novel or score < FAIR_MIN:
        grade = "poor"
    elif score < GOOD_MIN:
        grade = "fair"
    else:
        grade = "good"

    recognised = len(qu.technical_concepts) + len(qu.hints)
    notes: list[str] = []
    if qu.token_count <= 3:
        notes.append("Very short query: name the affected component, the symptom and when it happens.")
    elif qu.is_vague and grade != "good":
        notes.append("Vague wording: add the component, the symptom and the trigger to sharpen the match.")
    if recognised == 0:
        notes.append("No IT symptom, component or trigger was recognised in the text.")

    if grade == "good":
        summary = (f"Closely matches known incidents{' in family ' + fam['family_id'] if fam else ''}: the best match is "
                   f"{_pct(relevance)} relevant" + (f" and a fix is ranked at {_pct(fix)} confidence." if top else "."))
    elif grade == "fair":
        summary = (f"Partly relevant: the best match is {_pct(relevance)} relevant, but the pattern or fix evidence "
                   "is weaker than for a clear report.")
    elif novel:
        summary = (f"Nothing in the knowledge base is similar enough to act on (best match {_pct(relevance)} relevant, "
                   f"P(known) {known:.3f}). This is either a genuinely new incident or not an incident report "
                   "the knowledge base covers." if known is not None else
                   "Nothing in the knowledge base is similar enough to act on.")
    else:
        summary = f"Weak evidence: the best match is only {_pct(relevance)} relevant."

    return {
        "score": score, "grade": grade, "label": LABELS[grade], "summary": summary, "components": components,
        "clarity": {"specificity": qu.specificity, "tokens": qu.token_count, "is_vague": qu.is_vague,
                    "recognised_terms": recognised},
        "notes": notes,
        "bands": {"good": GOOD_MIN, "fair": FAIR_MIN},
        "basis": "Unweighted mean of the available components. The Good and Fair cut-offs are display bands, "
                 "not fitted thresholds; a novel verdict is always Poor.",
    }
