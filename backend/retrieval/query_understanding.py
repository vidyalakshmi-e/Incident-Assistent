"""Vague-to-technical query translation.

Engineers (and end users) describe incidents in natural language ("the system feels slow and
basic things take forever"). Before retrieval the query is expanded with technical concepts
(performance degradation, latency, timeout, resource exhaustion ...) using deterministic rules;
an LLM expansion is added only when an LLM is available and the rules found little.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.config.lexicon import (
    ENVIRONMENT_RULES, SCOPE_RULES, SYMPTOM_RULES, TRIGGER_RULES, COMPONENT_RULES, first_match, match_all,
)
from backend.retrieval.bm25_index import analyze

# Symptom combinations that imply extra concepts (documented heuristics).
COMBINATION_RULES = [
    ({"slow response", "freeze / hang"}, re.compile(r"restart\w* (?:it )?(?:fixes|helps|solves)|after (?:a )?restart it works|"
                                                     r"works again after (?:a )?restart|fixes it temporarily|comes back", re.I),
     ("memory leak", "resource exhaustion", "temporary workaround restart")),
]


@dataclass
class QueryUnderstanding:
    original: str
    expanded_query: str
    technical_concepts: list[str]
    matched_phrases: list[dict]
    hints: dict[str, str]
    token_count: int
    specificity: float
    is_vague: bool
    llm_expansion: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "original": self.original, "expanded_query": self.expanded_query,
            "technical_concepts": self.technical_concepts, "matched_phrases": self.matched_phrases,
            "hints": self.hints, "token_count": self.token_count, "specificity": self.specificity,
            "is_vague": self.is_vague, "llm_expansion": self.llm_expansion,
        }


def understand(query: str, extra_context: dict[str, str] | None = None, llm=None,
               vague_max_tokens: int = 9) -> QueryUnderstanding:
    text = query.strip()
    matched, concepts = [], []
    for rule in match_all(SYMPTOM_RULES, text):
        m = rule.pattern.search(text)
        matched.append({"phrase": m.group(0), "maps_to": rule.label, "concepts": list(rule.concepts)})
        concepts += rule.concepts
    labels = {m["maps_to"] for m in matched}
    for needed, pattern, extra in COMBINATION_RULES:
        if needed & labels and pattern.search(text):
            m = pattern.search(text)
            matched.append({"phrase": m.group(0), "maps_to": "restart-fixes-temporarily pattern", "concepts": list(extra)})
            concepts += extra
    hints: dict[str, str] = {}
    for name, rules in (("environment", ENVIRONMENT_RULES), ("impact_scope", SCOPE_RULES),
                        ("trigger", TRIGGER_RULES), ("component", COMPONENT_RULES)):
        r = first_match(rules, text)
        if r:
            hints[name] = r.label
    for k, v in (extra_context or {}).items():  # answers to clarifying questions override the text
        if v:
            hints[k] = v
    concepts = list(dict.fromkeys(concepts))

    llm_terms: list[str] = []
    if llm is not None and len(concepts) < 2:
        llm_terms = _llm_expand(llm, text)
        concepts += [t for t in llm_terms if t not in concepts]

    tokens = analyze(text)
    known = sum(1 for k in ("component", "environment", "impact_scope", "trigger") if k in hints) + (1 if matched else 0)
    specificity = round(min(1.0, known / 5 + min(len(tokens), 20) / 40), 3)
    is_vague = len(tokens) <= vague_max_tokens or specificity < 0.4
    hint_text = " ".join(v for k, v in hints.items() if k in ("component", "trigger"))
    expanded = " ".join([text] + concepts + ([hint_text] if hint_text else []))
    return QueryUnderstanding(text, expanded, concepts, matched, hints, len(tokens), specificity, is_vague, llm_terms)


def _llm_expand(llm, text: str) -> list[str]:
    """Ask the LLM for technical search terms (tagged as inferred in the evidence chain)."""
    prompt = ("Rewrite this IT incident report as 3 to 6 short technical search terms, comma-separated, "
              f"no explanation.\nReport: {text}")
    out = llm.complete(prompt, max_tokens=60, purpose="query_expansion")
    if not out:
        return []
    return [t.strip().strip(".").lower() for t in out.split(",") if 2 < len(t.strip()) < 40][:6]
