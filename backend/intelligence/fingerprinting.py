"""Enriched Incident Fingerprint — built once, reused by Pattern Intelligence, Novelty Detection,
Live Correlation and the Evidence Chain.

Ten fields, each with its own provenance and the evidence (phrase or source field) behind it:
  component, service, symptom, failure_type, trigger, root_cause, environment, dependency,
  business_impact, impact_scope

Provenance per value:
  derived   — rule applied to *real* text (Source A, an engineer's query) or real structured fields
  synthetic — rule applied to generated text (taint propagates from the input)
  missing   — no supporting signal; value is "Unknown". Nothing is invented.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.config.lexicon import (
    CI_GROUP_COMPONENT, COMPONENT_RULES, DEPENDENCY_RULES, ENVIRONMENT_RULES, ROOT_CAUSE_RULES, SCOPE_RULES,
    SYMPTOM_RULES, TRIGGER_RULES, extract_service, first_match, match_all,
)

FIELDS = ["component", "service", "symptom", "failure_type", "trigger", "root_cause", "environment",
          "dependency", "business_impact", "impact_scope"]
UNKNOWN = "Unknown"

CLOSURE_ROOT_CAUSE = {
    "hardware_fix": "hardware fault (per closure code)",
    "software_fix": "software fault (per closure code)",
    "data_fix": "data error (per closure code)",
    "user_or_operator": "user / operator error",
    "no_fault_found": "works as designed (no fault)",
}
CLOSURE_FAILURE_TYPE = {"no_fault_found": "no technical fault", "user_or_operator": "no technical fault"}

EFFECT = {
    "performance degradation": "degraded performance",
    "hard failure": "service unavailable",
    "intermittent failure": "intermittent service disruption",
    "resource exhaustion": "service disruption from exhausted resources",
    "functional failure": "business function not working",
    "data integrity": "incorrect business data",
    "security event": "security exposure",
    "no technical fault": "no service disruption (user expectation)",
}
SCOPE_PHRASE = {
    "organization-wide": "across the organization", "department": "for a department",
    "team": "for a team", "multiple users": "for multiple users", "limited (few users)": "for a few users",
    "single user": "for a single user", "minimal (single user)": "for a single user",
}


@dataclass
class Fingerprint:
    values: dict[str, str] = field(default_factory=lambda: {f: UNKNOWN for f in FIELDS})
    provenance: dict[str, str] = field(default_factory=lambda: {f: "missing" for f in FIELDS})
    evidence: dict[str, str] = field(default_factory=dict)
    symptoms: list[str] = field(default_factory=list)

    def set(self, name: str, value: str | None, prov: str, evidence: str) -> None:
        if value and value != UNKNOWN:
            self.values[name] = value
            self.provenance[name] = prov
            self.evidence[name] = evidence

    def known(self) -> list[str]:
        return [f for f in FIELDS if self.values[f] != UNKNOWN]

    def as_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Fingerprint":
        return cls(values=dict(d["values"]), provenance=dict(d["provenance"]),
                   evidence=dict(d.get("evidence", {})), symptoms=list(d.get("symptoms", [])))


def _hit(rules, text: str) -> tuple[str | None, str]:
    r = first_match(rules, text)
    if not r:
        return None, ""
    return r.label, r.pattern.search(text).group(0)


class Fingerprinter:
    version = "rules-v1"

    # ------------------------------------------------------------------ historical record
    def from_record(self, rec: dict) -> Fingerprint:
        fp = Fingerprint()
        text_prov = "synthetic" if rec.get("description_source") == "synthetic" else "derived"
        res_prov = "synthetic" if rec.get("resolution_notes_source") == "synthetic" else "derived"
        desc = f"{rec.get('title') or ''}. {rec.get('description') or ''}"
        res = str(rec.get("resolution_notes") or "")
        self._text_fields(fp, desc, text_prov)

        # component: text first, CI-derived fallback (real CI_Subcat)
        if fp.values["component"] == UNKNOWN:
            comp = CI_GROUP_COMPONENT.get(str(rec.get("ci_group")))
            fp.set("component", comp, "derived", f"CI_Subcat={rec.get('ci_subcategory')}")

        # root cause: resolution notes (engineer knowledge) → description → closure code
        label, phrase = _hit(ROOT_CAUSE_RULES, res)
        if label:
            fp.set("root_cause", label, res_prov, f"resolution notes: '{phrase}'")
        else:
            label, phrase = _hit(ROOT_CAUSE_RULES, desc)
            if label:
                fp.set("root_cause", label, text_prov, f"description: '{phrase}'")
            elif rec.get("closure_class") in CLOSURE_ROOT_CAUSE:
                fp.set("root_cause", CLOSURE_ROOT_CAUSE[rec["closure_class"]], "derived",
                       f"Closure_Code={rec.get('closure_code')}")

        # trigger: stated in text, else a real related-change record
        if fp.values["trigger"] == UNKNOWN:
            label, phrase = _hit(TRIGGER_RULES, res)
            if label:
                fp.set("trigger", label, res_prov, f"resolution notes: '{phrase}'")
        rc = rec.get("related_change")
        if fp.values["trigger"] == UNKNOWN and rc and str(rc) not in {"None", "nan", "Not Available"}:
            fp.set("trigger", "change (related change record)", "derived", f"Related_Change={rc}")

        if fp.values["dependency"] == UNKNOWN:
            label, phrase = _hit(DEPENDENCY_RULES, res)
            if label:
                fp.set("dependency", label, res_prov, f"resolution notes: '{phrase}'")

        if fp.values["failure_type"] == UNKNOWN and rec.get("closure_class") in CLOSURE_FAILURE_TYPE:
            fp.set("failure_type", CLOSURE_FAILURE_TYPE[rec["closure_class"]], "derived",
                   f"Closure_Code={rec.get('closure_code')}")

        # impact scope: text statement, else the real Impact field
        if fp.values["impact_scope"] == UNKNOWN and rec.get("impact_scope") not in (None, UNKNOWN):
            fp.set("impact_scope", rec["impact_scope"], "derived", f"Impact={rec.get('impact')}")
        self._business_impact(fp, rec.get("urgency"))
        return fp

    # ------------------------------------------------------------------ new incident / query
    def from_query(self, text: str, hints: dict[str, str] | None = None) -> Fingerprint:
        """Fingerprint of a new incident description (engineer-reported → 'derived').

        The root cause of a new incident is normally not in its description; it stays Unknown
        here and is inferred later from matched historical incidents (Evidence Chain)."""
        fp = Fingerprint()
        self._text_fields(fp, text, "derived")
        label, phrase = _hit(ROOT_CAUSE_RULES, text)
        if label:
            fp.set("root_cause", label, "derived", f"stated in report: '{phrase}'")
        for k, v in (hints or {}).items():
            if k in FIELDS and v and fp.values.get(k) == UNKNOWN:
                fp.set(k, v, "derived", "engineer answer to clarifying question")
        self._business_impact(fp, None)
        return fp

    # ------------------------------------------------------------------ helpers
    def _text_fields(self, fp: Fingerprint, text: str, prov: str) -> None:
        symptoms = match_all(SYMPTOM_RULES, text)
        fp.symptoms = [r.label for r in symptoms]
        if symptoms:
            primary = symptoms[0]
            fp.set("symptom", primary.label, prov, f"'{primary.pattern.search(text).group(0)}'")
            if primary.failure_type:
                fp.set("failure_type", primary.failure_type, prov, f"symptom '{primary.label}'")
        for name, rules in (("component", COMPONENT_RULES), ("trigger", TRIGGER_RULES),
                            ("environment", ENVIRONMENT_RULES), ("dependency", DEPENDENCY_RULES),
                            ("impact_scope", SCOPE_RULES)):
            label, phrase = _hit(rules, text)
            if label:
                fp.set(name, label, prov, f"'{phrase}'")
        svc = extract_service(text)
        if svc:
            fp.set("service", svc, prov, f"'{svc}'")

    def _business_impact(self, fp: Fingerprint, urgency) -> None:
        ft, scope = fp.values["failure_type"], fp.values["impact_scope"]
        if ft == UNKNOWN and scope == UNKNOWN:
            return
        effect = EFFECT.get(ft, "service impact")
        phrase = SCOPE_PHRASE.get(scope, "")
        text = f"{effect.capitalize()} {phrase}".strip()
        if str(urgency) in {"1", "2"}:
            text += " — urgent (Urgency " + str(urgency) + ")"
        weakest = "synthetic" if "synthetic" in (fp.provenance["failure_type"], fp.provenance["impact_scope"]) else "derived"
        fp.set("business_impact", text, weakest, "rule: failure_type × impact_scope (× urgency)")


def dimension_match(a: Fingerprint, b_values: dict[str, str] | dict[str, dict], field_name: str) -> float | None:
    """1/0 match of one field (None when either side is Unknown → not computable).

    `b_values` may be a flat {field: value} map (an incident) or a family signature
    {field: {value: share}}; for a family the match is the share of members with that value."""
    av = a.values.get(field_name, UNKNOWN)
    bv = b_values.get(field_name, UNKNOWN)
    if av == UNKNOWN or bv in (UNKNOWN, None, {}):
        return None
    if isinstance(bv, dict):
        return round(float(bv.get(av, 0.0)), 4)
    return 1.0 if av == bv else 0.0
