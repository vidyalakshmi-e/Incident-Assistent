"""Evidence Chain — a formal, reusable "why this recommendation" object.

Assembled at query time from the analysis bundle, the fingerprint store and the resolution ranking
(no dedicated table). Every field is populated only from real supporting data; otherwise it is
marked "insufficient evidence". Evidence-strength values are computed numbers, never LLM output.
Historical evidence and LLM inference are kept in separate sections.
"""
from __future__ import annotations

from collections import Counter

from backend.intelligence.fingerprinting import UNKNOWN
from backend.rag.llm import RETRIEVAL_ONLY_LABEL

INSUFFICIENT = "insufficient evidence"
TOP_N = 5


def _share_match(q_value: str, fps: list, field: str) -> dict:
    if q_value == UNKNOWN:
        return {"value": None, "status": INSUFFICIENT, "basis": f"incident {field} is Unknown"}
    known = [fp for fp in fps if fp is not None and fp.values.get(field, UNKNOWN) != UNKNOWN]
    if not known:
        return {"value": None, "status": INSUFFICIENT, "basis": f"no retrieved incident has a known {field}"}
    if field == "symptom":
        hits = sum(1 for fp in known if q_value == fp.values["symptom"] or q_value in fp.symptoms)
    else:
        hits = sum(1 for fp in known if fp.values[field] == q_value)
    return {"value": round(hits / len(known), 4), "status": "computed",
            "basis": f"{hits}/{len(known)} of the top retrieved incidents with a known {field} match '{q_value}'"}


def root_cause_evidence(rt, retrieved_ids: list[str]) -> dict:
    rows = []
    for iid in retrieved_ids:
        fp = rt.patterns.fingerprint_of(iid)
        if fp and fp.values["root_cause"] != UNKNOWN:
            rows.append({"incident_id": iid, "root_cause": fp.values["root_cause"],
                         "provenance": fp.provenance["root_cause"], "from": fp.evidence.get("root_cause", "")})
    if not rows:
        return {"status": INSUFFICIENT}
    top, n = Counter(r["root_cause"] for r in rows).most_common(1)[0]
    support = [r for r in rows if r["root_cause"] == top]
    share = n / len(retrieved_ids)
    return {"status": "computed", "statement": top,
            "certainty": "likely" if share >= 0.6 else ("possible" if share >= 0.3 else "weakly supported"),
            "share_of_retrieved": round(share, 3), "supporting_incidents": [r["incident_id"] for r in support],
            "fields": [f"{r['incident_id']}.fingerprint.root_cause ← {r['from']} ({r['provenance']})" for r in support],
            "provenance_breakdown": dict(Counter(r["provenance"] for r in support)),
            "note": "Root cause of a NEW incident is inferred from matched historical incidents; it is not observed."}


def assemble(rt, bundle, ranking: dict | None = None, synthesis: dict | None = None,
             validation: dict | None = None, subject: str = "recommendation") -> dict:
    res = bundle.retrieval.results
    top_ids = [r.incident_id for r in res[:TOP_N]]
    hist_fps = [rt.patterns.fingerprint_of(i) for i in top_ids]
    qfp = bundle.fingerprint
    fam = bundle.families[0] if bundle.families else None
    chain: dict = {"subject": subject}

    novel = bool(bundle.novelty.get("is_novel"))
    chain["query_understood"] = {**bundle.qu.as_dict(),
                                 "llm_expansion_tag": "inferred" if bundle.qu.llm_expansion else None}
    chain["extracted_fingerprint"] = qfp.as_dict()
    if novel:
        chain["matched_incident_family"] = {
            "status": INSUFFICIENT, "reason": bundle.novelty.get("verdict"),
            "nearest_family_below_threshold": ({k: fam[k] for k in ("family_id", "name", "match_strength")} if fam else None),
            "novelty": {k: bundle.novelty.get(k) for k in ("verdict", "is_novel", "known_probability", "threshold")}}
    elif fam and fam.get("match_strength") is not None:
        chain["matched_incident_family"] = {
            "family_id": fam["family_id"], "name": fam["name"], "match_strength": fam["match_strength"],
            "vote_share": fam["vote_share"], "max_relevance": fam["max_relevance"],
            "centroid_similarity": fam["centroid_similarity"], "supporting_incidents": fam["supporting_incidents"],
            "runner_up": ({k: bundle.families[1][k] for k in ("family_id", "name", "match_strength")}
                          if len(bundle.families) > 1 else None),
            "novelty": {k: bundle.novelty.get(k) for k in ("verdict", "is_novel", "known_probability", "threshold")},
        }
    else:
        chain["matched_incident_family"] = {"status": INSUFFICIENT,
                                            "novelty": {k: bundle.novelty.get(k) for k in ("verdict", "is_novel")}}
    chain["retrieved_incidents"] = [{
        "incident_id": r.incident_id, "rank": r.rank, "relevance_confidence": r.scores.relevance_confidence,
        "why_retrieved": r.why_retrieved.summary, "retrievers": r.why_retrieved.retrievers,
        "matched_terms": r.why_retrieved.matched_terms[:8], "matched_concepts": r.why_retrieved.matched_concepts,
        "family": rt.patterns.assign.get(r.incident_id), "text_provenance": r.provenance.get("description"),
        "quality_tier": r.quality.get("tier"), "duplicates_collapsed": r.duplicates_collapsed,
    } for r in res[:TOP_N]] or [{"status": INSUFFICIENT}]
    if novel:
        chain["root_cause_evidence"] = {"status": INSUFFICIENT,
                                        "reason": "novel incident — nearest historical incidents are below the "
                                                  "similarity threshold, so their root causes are not evidence"}
    else:
        chain["root_cause_evidence"] = root_cause_evidence(rt, top_ids) if top_ids else {"status": INSUFFICIENT}

    top = None if novel else (ranking or {}).get("top")
    if top:
        chain["resolution_evidence"] = {
            "status": "computed", "recommended_action": top["action"], "strategy_key": top["strategy_key"],
            "kind": top["kind"], "supporting_incidents": top["supporting_incidents"],
            "evidence": [{k: e[k] for k in ("incident_id", "relevance_confidence", "influence_weight", "text_provenance",
                                             "quality_tier")} for e in top["evidence"]],
            "confidence": top["confidence"], "confidence_components": top["confidence_components"],
            "confidence_basis": top["confidence_basis"], "evidence_provenance": top["evidence_provenance"],
            "strategy_outcome_stats": top.get("strategy_stats"), "safety": top["safety"],
        }
    else:
        chain["resolution_evidence"] = {"status": INSUFFICIENT, **({"reason": "novel incident — route to fresh "
                                                                             "investigation, no historical fix recommended"}
                                                                  if novel else {})}

    chain["evidence_strength"] = {
        "component_match": _share_match(qfp.values["component"], hist_fps, "component"),
        "symptom_match": _share_match(qfp.values["symptom"], hist_fps, "symptom"),
        "environment_match": _share_match(qfp.values["environment"], hist_fps, "environment"),
        "pattern_match": ({"value": fam["match_strength"], "status": "computed",
                           "basis": "family vote share × best relevance confidence"
                                    + (" (below novelty threshold)" if novel else "")}
                          if fam and fam.get("match_strength") is not None
                          else {"value": None, "status": INSUFFICIENT, "basis": "no calibrated family match"}),
    }
    # historical evidence vs LLM inference — kept visibly separate
    chain["llm_inference"] = {
        "available": rt.llm.available,
        "label": None if rt.llm.available else RETRIEVAL_ONLY_LABEL,
        "query_expansion": bundle.qu.llm_expansion or None,
        "synthesis": synthesis, "validation": validation,
        "tag": "inferred (LLM) — not historical evidence",
    }
    chain["mode"] = {"labels": list(bundle.retrieval.mode.labels) + ([] if rt.llm.available else [RETRIEVAL_ONLY_LABEL]),
                     "embedder": bundle.retrieval.mode.embedder, "reranker": bundle.retrieval.mode.reranker,
                     "notes": bundle.retrieval.mode.notes}
    core = ["matched_incident_family", "root_cause_evidence", "resolution_evidence"]
    strength = chain["evidence_strength"]
    filled = [k for k in core if chain[k].get("status") != INSUFFICIENT] + \
             [f"evidence_strength.{k}" for k, v in strength.items() if v["status"] == "computed"]
    missing = [k for k in core if chain[k].get("status") == INSUFFICIENT] + \
              [f"evidence_strength.{k}" for k, v in strength.items() if v["status"] != "computed"]
    chain["completeness"] = {"populated": filled, "insufficient": missing,
                             "ratio": round(len(filled) / (len(filled) + len(missing)), 3),
                             "complete_core": all(chain[k].get("status") != INSUFFICIENT for k in core)}
    return chain
