"""Ranked primary resolution (RESOLUTION OUTPUT RULE).

The Incident Assistant always leads with ONE top-ranked, actionable resolution. Alternatives are
kept for the fallback path (a failed step → next-best) and the separate strategy panel.

Ranking: retrieved incidents with a usable resolution note are grouped by their historical
strategy (strategy.py). Each group's evidence mass is

    mass(g) = Σ_i relevance_confidence_i × influence_weight_i

where influence_weight = knowledge-quality score × provenance factor (original 1.0, synthetic 0.8),
so poor-quality or generated records have reduced influence.

Confidence of a recommendation (real, derived — never LLM-guessed):

    confidence = max_relevance(g) × agreement(g) × provenance_factor(g)
    agreement(g) = mass(g) / Σ mass       (share of the evidence backing this strategy)

When results are unreranked there is no calibrated relevance, so confidence is "undetermined".
"""
from __future__ import annotations

import re

from backend.knowledge.quality import resolution_detail
from backend.rag.guardrails import safety_review
from backend.rag.strategy import StrategyIndex, action_summary
from backend.schemas.retrieval import RetrievedIncident

PROV_FACTOR = {"original": 1.0, "synthetic": 0.8}


OBSERVE = re.compile(r"(back to normal|verified|confirmed|no (?:more|further|longer)|stable|dropp\w*|reduc\w*|"
                     r"restored|succe\w+|works? again|normal|operational|below|cleared|reconcil\w*|flat|passed|"
                     r"can (?:log in|work|print|send)|available again)", re.I)


def expected_observation(note: str) -> str | None:
    """The verification clause of a historical note (what the engineer should see if it worked)."""
    clauses = [c.strip(" .;,") for c in re.split(r"(?<=[.;])\s+|,\s+(?:and\s+)?|;\s*", note or "") if c.strip(" .;,")]
    for c in reversed(clauses):  # verification usually comes last
        if OBSERVE.search(c):
            return c[0].upper() + c[1:]
    return None


FAMILY_PRIOR_MIN_STRENGTH = 0.5


def rank_resolutions(results: list[RetrievedIncident], sidx: StrategyIndex, excluded_keys: set[str] | None = None,
                     reranked: bool = True, family: dict | None = None) -> dict:
    """`family` (the top pattern match) adds a prior: when the incident is confidently matched to a
    family (match strength ≥ 0.5), evidence for that family's own strategies is weighted by
    (1 + match_strength). After a failed step this makes the *other historical approaches of the
    same pattern* the next candidates, instead of drifting to unrelated families."""
    excluded_keys = excluded_keys or set()
    groups: dict[str, dict] = {}
    skipped_low_quality = []
    for r in results:
        note = r.resolution_notes or ""
        if resolution_detail(note)[0] <= 0.2:
            skipped_low_quality.append(r.incident_id)
            continue
        key = sidx.key_for(r.incident_id)
        if key in excluded_keys:
            continue
        c = r.scores.relevance_confidence
        w = float(r.quality.get("influence_weight", 0.5))
        g = groups.setdefault(key, {"strategy_key": key, "supporting": []})
        g["supporting"].append({
            "incident_id": r.incident_id, "relevance_confidence": c, "influence_weight": w,
            "quality_tier": r.quality.get("tier"), "text_provenance": r.provenance.get("resolution_notes", "missing"),
            "note": note, "duplicates": r.duplicates_collapsed,
        })
    fam_id = family.get("family_id") if family else None
    fam_strength = float(family.get("match_strength") or 0.0) if family else 0.0
    use_prior = fam_id is not None and fam_strength >= FAMILY_PRIOR_MIN_STRENGTH
    for g in groups.values():
        rel = [s["relevance_confidence"] if s["relevance_confidence"] is not None else 0.5 for s in g["supporting"]]
        g["evidence_mass"] = sum(x * s["influence_weight"] for x, s in zip(rel, g["supporting"]))
        g["in_family"] = bool(use_prior and g["strategy_key"].startswith(f"{fam_id}-"))
        g["mass"] = g["evidence_mass"] * ((1 + fam_strength) if g["in_family"] else 1.0)
        g["max_relevance"] = max(rel)
    total = sum(g["mass"] for g in groups.values()) or 1.0
    ranked, blocked = [], []
    for g in sorted(groups.values(), key=lambda g: -g["mass"]):
        best = max(g["supporting"], key=lambda s: (s["relevance_confidence"] or 0) * s["influence_weight"])
        strat = sidx.by_key.get(g["strategy_key"])
        label = action_summary(best["note"])  # concrete action of the best-supported note
        provs = [s["text_provenance"] for s in g["supporting"]]
        pf = sum(PROV_FACTOR.get(p, 0.8) for p in provs) / len(provs)
        agreement = g["mass"] / total
        conf = round(g["max_relevance"] * agreement * pf, 4) if reranked else None
        safety = safety_review(f"{label}. {best['note']}", n_independent_sources=len(g["supporting"]))
        item = {
            "strategy_key": g["strategy_key"], "action": label, "step": best["note"],
            "strategy_label": strat["label"] if strat else label,
            "expected_observation": expected_observation(best["note"]),
            "supporting_incidents": [s["incident_id"] for s in g["supporting"]],
            "evidence": g["supporting"],
            "confidence": conf,
            "confidence_components": {"max_relevance": round(g["max_relevance"], 4), "agreement": round(agreement, 4),
                                      "provenance_factor": round(pf, 3)} if reranked else None,
            "matched_family_strategy": g["in_family"],
            "confidence_basis": ("max calibrated relevance × evidence agreement × provenance factor" if reranked
                                 else "undetermined — results are unreranked, no calibrated relevance available"),
            "evidence_provenance": {"original": provs.count("original"), "synthetic": provs.count("synthetic")},
            "kind": "observed historical resolution" if strat else "single historical resolution",
            "strategy_stats": ({k: strat.get(k) for k in ("n_incidents", "reopen_rate", "reopen_ci_low", "reopen_ci_high",
                                                          "median_resolution_hours", "stats_supported", "basis")}
                               if strat else None),
            "safety": safety,
        }
        (ranked if safety["allowed"] else blocked).append(item)
    return {
        "top": ranked[0] if ranked else None,
        "alternatives": ranked[1:],
        "blocked_by_guardrails": blocked,
        "excluded_strategies": sorted(excluded_keys),
        "skipped_low_quality_notes": skipped_low_quality,
        "evidence_mass_total": round(total, 4),
    }
