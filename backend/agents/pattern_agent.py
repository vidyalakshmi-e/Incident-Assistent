"""Pattern Intelligence Agent.

Scope: *what is this incident?* Tools: query understanding + hybrid retrieval (read-only),
Fingerprinter, PatternEngine (family match), causal-chain store, NoveltyDetector.
It never proposes fixes and never touches attempt/escalation records.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.agents.messages import msg
from backend.services.analysis import analyze_text


@lru_cache(maxsize=1)
def _chains(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class PatternIntelligenceAgent:
    name = "pattern_intelligence_agent"
    tools = ["hybrid_retrieval(read-only)", "fingerprinter", "pattern_engine.match", "causal_chain_store", "novelty_detector"]

    def __init__(self, rt):
        self.rt = rt

    def causal_chain(self, incident_id: str) -> dict | None:
        return _chains(str(self.rt.s.processed_dir / "causal_chains.json")).get(incident_id)

    def family_chain(self, family_id: str) -> list | None:
        fam = self.rt.patterns.families.get(family_id)
        return fam.extra.get("causal_chain") if fam else None

    def run(self, state: dict) -> dict:
        bundle = analyze_text(self.rt, state["text"], filters=state.get("filters"), hints=state.get("hints"),
                              top_k=state.get("top_k", 10), pool=state.get("pool"))
        fam = bundle.families[0] if bundle.families else None
        ctx = {
            "fingerprint": bundle.fingerprint.as_dict(),
            "families": [{k: f[k] for k in ("family_id", "name", "size", "status", "vote_share", "max_relevance",
                                            "centroid_similarity", "match_strength", "supporting_incidents")}
                         for f in bundle.families[:3]],
            "family_causal_chain": self.family_chain(fam["family_id"]) if fam else None,
            "novelty": bundle.novelty,
        }
        novel = bool(bundle.novelty.get("is_novel"))
        if novel:
            m = msg(self.name, "escalation_agent", "NOVEL_INCIDENT",
                    "No sufficiently similar historical incident — route to fresh investigation",
                    known_probability=bundle.novelty.get("known_probability"))
        else:
            m = msg(self.name, "diagnostic_agent", "PATTERN_CONTEXT",
                    f"Matched {fam['family_id']} ({fam['name']})" if fam else "No family matched",
                    family_id=fam["family_id"] if fam else None,
                    match_strength=fam["match_strength"] if fam else None)
        return {"bundle": bundle, "pattern": ctx, "messages": [m], "route": "escalation" if novel else "diagnostic"}
