"""Causal Chain representation — a formal output of the Pattern Intelligence Engine.

    Trigger → Technical Failure → Symptom → Business Impact → Resolution → Outcome

Every link carries exactly one tag (documented rules):

  observed — directly supported by real recorded data: a real related-change record, the
             verbatim symptom / resolution text of an original ticket, real timestamps
  derived  — computed from real fields by a documented rule (Closure_Code → failure class,
             Impact/Urgency → business impact, rule extraction from original text)
  inferred — reconstructed from generated (synthetic/LLM) text or by an LLM; not confirmed by data

No chain is built for an incident without temporal ordering data (no Open/Resolved timestamps):
the unordered facts are returned instead with `available=False` and the reason.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

import pandas as pd

from backend.intelligence.fingerprinting import UNKNOWN, Fingerprint

STAGES = ["trigger", "technical_failure", "symptom", "business_impact", "resolution", "outcome"]
TAG_WEIGHT = {"observed": 1.0, "derived": 0.75, "inferred": 0.4}


@dataclass
class ChainLink:
    stage: str
    statement: str
    tag: str
    evidence: str

    def as_dict(self) -> dict:
        return asdict(self)


def _text_tag(source: str | None) -> str:
    return "inferred" if source == "synthetic" else "observed"


def _rule_tag(prov: str) -> str:
    return "inferred" if prov == "synthetic" else "derived"


def build_incident_chain(rec: dict, fp: Fingerprint) -> dict:
    links: list[ChainLink] = []
    # ---- trigger
    rc = rec.get("related_change")
    if rc and str(rc) not in {"None", "nan", "Not Available"}:
        links.append(ChainLink("trigger", f"Change record {rc} is linked to this incident "
                               "(the link is recorded; whether it caused the incident is not)", "observed",
                               "Related_Change field"))
    elif fp.values["trigger"] != UNKNOWN:
        links.append(ChainLink("trigger", fp.values["trigger"], _rule_tag(fp.provenance["trigger"]),
                               fp.evidence.get("trigger", "")))
    # ---- technical failure
    if fp.values["root_cause"] != UNKNOWN:
        prov = fp.provenance["root_cause"]
        ev = fp.evidence.get("root_cause", "")
        tag = "derived" if ev.startswith("Closure_Code") else _rule_tag(prov)
        links.append(ChainLink("technical_failure", fp.values["root_cause"], tag, ev))
    # ---- symptom
    if rec.get("description"):
        links.append(ChainLink("symptom", str(rec["description"])[:220], _text_tag(rec.get("description_source")),
                               "incident description" + (" (generated text)" if rec.get("description_source") == "synthetic" else "")))
    # ---- business impact
    if rec.get("impact") not in (None, "Not Set") or rec.get("urgency") not in (None, "Not Set"):
        links.append(ChainLink("business_impact", fp.values["business_impact"] if fp.values["business_impact"] != UNKNOWN
                               else f"Impact {rec.get('impact')} / Urgency {rec.get('urgency')}", "derived",
                               f"Impact={rec.get('impact')}, Urgency={rec.get('urgency')} (ITIL fields)"))
    elif fp.values["business_impact"] != UNKNOWN:
        links.append(ChainLink("business_impact", fp.values["business_impact"],
                               _rule_tag(fp.provenance["business_impact"]), "rule on text"))
    # ---- resolution
    if rec.get("resolution_notes"):
        cc = rec.get("closure_code")
        extra = f" [closure code: {cc}]" if cc and cc != "Not Set" else ""
        links.append(ChainLink("resolution", str(rec["resolution_notes"])[:220] + extra,
                               _text_tag(rec.get("resolution_notes_source")),
                               "resolution notes" + (" (generated text)" if rec.get("resolution_notes_source") == "synthetic" else "")))
    # ---- outcome
    ot, rt, rp = rec.get("open_time"), rec.get("resolved_time"), rec.get("reopen_time")
    has_time = ot is not None and not pd.isna(ot) and rt is not None and not pd.isna(rt)
    if has_time:
        hours = (pd.Timestamp(rt) - pd.Timestamp(ot)).total_seconds() / 3600
        stmt = f"Resolved {hours:.1f} h after opening"
        if rp is not None and not pd.isna(rp):
            stmt += f"; reopened on {pd.Timestamp(rp):%Y-%m-%d %H:%M} (fix did not hold)"
        else:
            stmt += "; not reopened"
        reas = rec.get("no_of_reassignments")
        if reas is not None and not pd.isna(reas):
            stmt += f"; {int(reas)} reassignment(s)"
        links.append(ChainLink("outcome", stmt, "observed", "Open_Time / Resolved_Time / Reopen_Time timestamps"))

    ordered = sorted(links, key=lambda l: STAGES.index(l.stage))
    if not has_time:
        return {
            "incident_id": rec.get("incident_id"), "available": False,
            "reason": "No Open/Resolved timestamps for this incident, so temporal ordering cannot be observed. "
                      "The facts below are shown unordered and no causal chain is claimed.",
            "facts": [l.as_dict() for l in ordered], "links": [],
        }
    missing = [s for s in STAGES if s not in {l.stage for l in ordered}]
    return {
        "incident_id": rec.get("incident_id"), "available": True,
        "temporal_ordering": {"tag": "observed", "open_time": str(ot), "resolved_time": str(rt),
                              "reopen_time": None if rp is None or pd.isna(rp) else str(rp)},
        "links": [l.as_dict() for l in ordered],
        "missing_stages": missing,
        "tag_counts": dict(Counter(l.tag for l in ordered)),
        "chain_strength": round(sum(TAG_WEIGHT[l.tag] for l in ordered) / len(STAGES), 3),
    }


def build_family_chain(chains: list[dict]) -> list[dict]:
    """Aggregate member chains: for each stage the most common statement class, its share, and
    the tag distribution. Only members with an available (timestamped) chain contribute."""
    usable = [c for c in chains if c.get("available")]
    out = []
    for stage in STAGES:
        items = [l for c in usable for l in c["links"] if l["stage"] == stage]
        if not items:
            out.append({"stage": stage, "statement": "insufficient evidence", "share": 0.0,
                        "support": 0, "tags": {}})
            continue
        if stage in ("symptom", "resolution"):
            stmt = f"{len(items)} member records ({stage} text varies by incident)"
        elif stage == "outcome":
            reopened = sum("reopened" in l["statement"] and "not reopened" not in l["statement"] for l in items)
            stmt = f"{len(items)} resolved; {reopened} reopened ({reopened / len(items):.1%})"
        else:
            stmt, _ = Counter(l["statement"] for l in items).most_common(1)[0]
        top_share = Counter(l["statement"] for l in items).most_common(1)[0][1] / len(items) \
            if stage not in ("symptom", "resolution", "outcome") else 1.0
        tags = Counter(l["tag"] for l in items)
        out.append({"stage": stage, "statement": stmt, "share": round(top_share, 3), "support": len(items),
                    "coverage": round(len(items) / max(1, len(usable)), 3),
                    "tags": {k: round(v / len(items), 3) for k, v in tags.items()}})
    return out
