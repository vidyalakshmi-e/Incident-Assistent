"""Clarification Before Escalation.

Before committing to a low-confidence answer, or before escalating when the troubleshooting loop is
about to run out of rounds, check whether ONE short, targeted question would sharpen the match.

Trigger conditions, checked in this order:
  1. low_confidence_vague  — top match confidence < threshold AND the query is short / vague
  2. ambiguous_families    — top-2 families match with similar strength AND a fingerprint field
                             that separates them is still Unknown for this incident
  3. pre_escalation        — the loop is about to exhaust its round cap AND a useful field is missing

Rules: at most one question per turn; at most `max_clarifications_per_session` (default 1) per
session, so this adds at most one round-trip; never ask about a field the fingerprint or an
earlier answer already covers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from backend.config.lexicon import COMPONENT_RULES, ENVIRONMENT_RULES, SCOPE_RULES, TRIGGER_RULES, first_match
from backend.intelligence.fingerprinting import UNKNOWN

QUESTIONS = {
    "impact_scope": ("Is this affecting a single user or multiple users?",
                     ["single user", "multiple users", "a whole team", "the whole organization"]),
    "trigger": ("Did this start after a recent deployment or configuration change?",
                ["yes, after a deployment / release", "yes, after a configuration change", "after patching / maintenance", "no recent change"]),
    "environment": ("Which environment is this in — production, staging, or development?",
                    ["production", "staging", "development"]),
    "component": ("Which system or component is affected (application, database, network, laptop, ...)?",
                  ["application", "database", "network / VPN", "laptop / workstation", "storage"]),
}
# fields asked in this priority order when the query is vague
VAGUE_PRIORITY = ["component", "impact_scope", "trigger", "environment"]
SEPARATING_FIELDS = ["component", "trigger", "impact_scope", "environment", "symptom"]
FIELD_RULES = {"impact_scope": SCOPE_RULES, "trigger": TRIGGER_RULES, "environment": ENVIRONMENT_RULES,
               "component": COMPONENT_RULES}
CHOICE_MAP = {
    "single user": "single user", "multiple users": "multiple users", "a whole team": "team",
    "the whole organization": "organization-wide",
    "yes, after a deployment / release": "deployment / release", "yes, after a configuration change": "configuration change",
    "after patching / maintenance": "patching / maintenance", "no recent change": "no recent change",
    "production": "Production", "staging": "Staging", "development": "Development",
    "application": "Application", "database": "Database", "network / vpn": "Network",
    "laptop / workstation": "End-user device", "storage": "Storage",
}


@dataclass
class Clarification:
    field: str
    question: str
    options: list[str]
    trigger: str
    reason: str

    def as_dict(self) -> dict:
        return asdict(self)


def _known(field: str, fingerprint_values: dict, answered: dict) -> bool:
    return field in answered or fingerprint_values.get(field, UNKNOWN) != UNKNOWN


def _dominant(sig: dict, field: str) -> str | None:
    for v, share in (sig.get(field) or {}).items():
        if v != UNKNOWN and share >= 0.3:
            return v
    return None


class ClarificationPolicy:
    def __init__(self, confidence_threshold: float, family_margin: float, max_per_session: int):
        self.threshold = confidence_threshold
        self.margin = family_margin
        self.max_per_session = max_per_session

    def check(self, *, top_confidence: float | None, is_vague: bool, families: list[dict], fingerprint_values: dict,
              answered: dict, asked_count: int, about_to_escalate: bool = False) -> Clarification | None:
        if asked_count >= self.max_per_session:
            return None
        # 1. low confidence + vague query
        low = top_confidence is None or top_confidence < self.threshold
        if low and is_vague and not about_to_escalate:
            for f in VAGUE_PRIORITY:
                if not _known(f, fingerprint_values, answered):
                    q, opts = QUESTIONS[f]
                    conf_txt = "undetermined" if top_confidence is None else f"{top_confidence:.2f}"
                    return Clarification(f, q, opts, "low_confidence_vague",
                                         f"match confidence {conf_txt} < {self.threshold} and the report is short/vague")
        # 2. ambiguous families
        strong = [f for f in families if (f.get("match_strength") or 0) > 0]
        if len(strong) >= 2 and not about_to_escalate:
            a, b = strong[0], strong[1]
            if a["match_strength"] - b["match_strength"] <= self.margin:
                for f in SEPARATING_FIELDS:
                    va, vb = _dominant(a["signature"], f), _dominant(b["signature"], f)
                    if va and vb and va != vb and not _known(f, fingerprint_values, answered) and f in QUESTIONS:
                        q, opts = QUESTIONS[f]
                        return Clarification(f, q, opts, "ambiguous_families",
                                             f"families {a['family_id']} ({a['match_strength']:.2f}) and {b['family_id']} "
                                             f"({b['match_strength']:.2f}) are within {self.margin}; they differ on {f} "
                                             f"('{va}' vs '{vb}')")
        # 3. about to escalate
        if about_to_escalate:
            for f in ["trigger", "impact_scope", "environment", "component"]:
                if not _known(f, fingerprint_values, answered):
                    q, opts = QUESTIONS[f]
                    return Clarification(f, q, opts, "pre_escalation",
                                         "the troubleshooting loop is about to reach its round cap; this detail may "
                                         "allow one more targeted suggestion before handing off")
        return None


def parse_answer(field: str, answer: str) -> str | None:
    """Map an engineer's answer (a listed option or free text) to a fingerprint value."""
    a = (answer or "").strip()
    if not a:
        return None
    if a.lower() in CHOICE_MAP:
        return CHOICE_MAP[a.lower()]
    rules = FIELD_RULES.get(field)
    if rules:
        r = first_match(rules, a)
        if r:
            return r.label
    if field == "trigger" and a.lower().startswith("no"):
        return "no recent change"
    return None
