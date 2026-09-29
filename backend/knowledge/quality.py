"""Knowledge Base Quality Manager.

Runs *before* fingerprinting / pattern intelligence (those depend on clean input) and again on
every record entering the KB through the evolution loop. It identifies:

* empty, extremely short and generic ("closed", "fixed") resolution notes
* exact and near-duplicate incidents
* contradictory information (text vs. category, closure code vs. resolution note, resolution
  that is inconsistent with how similar incidents were resolved, priority-matrix violations)

and assigns a knowledge-quality score in [0, 1]. The score reduces a record's influence during
resolution synthesis (see rag/resolution.py). This is supporting infrastructure, not a headline
feature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

GENERIC_NOTES = {
    "closed", "fixed", "resolved", "done", "ok", "ok now", "solved", "issue resolved, closing ticket",
    "user confirmed, closed", "see previous call", "no further action", "works again", "restarted",
    "solved - see call", "closing", "n/a", "na", "-",
}
ACTION = re.compile(r"\b(restart|recycl|replac|swap|install|increas|extend|configur|set |rolled back|roll back|"
                    r"rollback|deploy|patch|hotfix|reset|clear|rebuil|reimag|import|renew|updat|upgrad|"
                    r"moved|archiv|created|added|fixed|correct|unlock|explain|rerun|reran|resync|disabl|"
                    r"enabl|reinstall|power-cycl|gather|kill|terminat|block|enforc|optimi|refresh|expand|tun(?:e|ed|ing)\b|"
                    r"capp|lower|rais|rescan|drain|logged|remov|synchroni|align|dispatch|implement|appl(?:y|ied)|"
                    r"reschedul|start(?:ed)?\b|swapp|reimag|repair|re-?enabl|reconfigur|escalat)", re.I)
CAUSE = re.compile(r"\b(root cause|caused by|due to|because|was (?:full|stale|missing|corrupt|expired|"
                   r"overloaded|exhausted|capped|broken|stuck|hung)|turned out|leak|defect|misconfig|"
                   r"mismatch|expired)", re.I)
VERIFY = re.compile(r"\b(verif|confirm|monitor|test(?:ed)? |back to normal|stable|no (?:more|further) "
                    r"(?:errors|alerts|timeouts)|works again|resolved|since)", re.I)

HARDWARE_FIX = re.compile(r"\b(replac\w*|swapp?ed|supplier|field engineer|hardware|module|sfp|cable|hba|"
                          r"fuser|loan laptop|defect)", re.I)
SOFTWARE_FIX = re.compile(r"\b(patch\w*|hotfix|upgrad\w*|install\w*|roll(?:ed)? ?back|release|configur\w*|"
                          r"restart\w*|recycl\w*|transport|sap note|driver|feature toggle|heap|pool|"
                          r"certificate|policy|job)", re.I)
USER_FIX = re.compile(r"\b(explain\w*|instruction|procedure|walk(?:ed)? the user|by design|functional owner|"
                      r"informed the user|change request|enhancement|work instruction|runbook)", re.I)


@dataclass
class QualityResult:
    score: float
    tier: str
    flags: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s).lower())).strip()


def resolution_detail(note: str | None) -> tuple[float, list[str]]:
    if note is None or not str(note).strip():
        return 0.0, ["empty_resolution"]
    n = str(note).strip()
    norm = normalize_text(n)
    words = len(norm.split())
    if norm in {normalize_text(g) for g in GENERIC_NOTES}:
        return 0.05, ["generic_resolution"]
    flags = ["too_short"] if words < 4 else []
    length = min(1.0, words / 15)
    score = 0.4 * length + 0.25 * bool(ACTION.search(n)) + 0.2 * bool(CAUSE.search(n)) + 0.15 * bool(VERIFY.search(n))
    if not ACTION.search(n):
        flags.append("no_concrete_action")
    return round(float(score), 4), flags


def closure_note_conflict(closure_class: str | None, note: str | None) -> bool:
    """True when the closure code and the resolution note describe different kinds of fix."""
    if not note or not closure_class:
        return False
    hw, sw, us = bool(HARDWARE_FIX.search(note)), bool(SOFTWARE_FIX.search(note)), bool(USER_FIX.search(note))
    if closure_class == "hardware_fix":
        return (sw or us) and not hw
    if closure_class == "software_fix":
        return hw and not sw
    if closure_class == "user_or_operator":
        return (hw or sw) and not us
    if closure_class == "no_fault_found":
        return (hw or sw) and not us
    return False


def exact_duplicate_groups(kb: pd.DataFrame) -> pd.Series:
    key = (kb["title"].map(normalize_text) + "|" + kb["description"].map(normalize_text) + "|"
           + kb["resolution_notes"].map(normalize_text))
    first = {}
    groups = []
    for iid, k in zip(kb["incident_id"], key):
        first.setdefault(k, iid)
        groups.append(first[k])
    return pd.Series(groups, index=kb.index)


def near_duplicate_groups(ids: list[str], emb: np.ndarray, threshold: float = 0.95) -> list[str]:
    """Connected components over pairs with cosine >= threshold (embeddings are L2-normalized)."""
    n = len(ids)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for start in range(0, n, 512):
        sims = emb[start:start + 512] @ emb.T
        rows, cols = np.nonzero(sims >= threshold)
        for r, c in zip(rows + start, cols):
            if r < c:
                ra, rb = find(r), find(c)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    return [ids[find(i)] for i in range(n)]


def mask_entities(text: str, ci_name: str | None) -> str:
    """Mask the CI name and known service names before comparing texts, so a wrong note that
    merely mentions the same server does not look consistent with the incident."""
    t = str(text or "")
    if ci_name:
        t = t.replace(str(ci_name), "the system")
    for svc in _service_names():
        t = re.sub(re.escape(svc), "the service", t, flags=re.I)
    return t


def _service_names() -> list[str]:
    from backend.data_pipeline.scenarios import SCENARIOS

    return sorted({s for sc in SCENARIOS for s in sc.services}, key=len, reverse=True)


def resolution_consistency(desc_emb: np.ndarray, res_emb: np.ndarray, dup_group: list[str],
                           usable: np.ndarray, k: int = 10) -> np.ndarray:
    """For each record: the best cosine between its (entity-masked) resolution and the resolutions
    of its k nearest neighbours by (entity-masked) description, excluding its own exact-duplicate
    group and records whose notes are too poor to compare. A resolution that resembles *none* of
    the ways similar incidents were fixed is a contradiction candidate."""
    out = np.ones(len(desc_emb), dtype=np.float32)
    groups = np.asarray(dup_group)
    for start in range(0, len(desc_emb), 512):
        sims = desc_emb[start:start + 512] @ desc_emb.T
        for j, row in enumerate(sims):
            i = start + j
            row = row.copy()
            row[groups == groups[i]] = -np.inf
            row[~usable] = -np.inf
            nn = np.argpartition(-row, k)[:k]
            out[i] = float(np.max(res_emb[nn] @ res_emb[i]))
    return out


CONSISTENCY_PERCENTILE = 5  # flag the least consistent 5% of comparable notes (data-driven fence)


def low_fence(values: np.ndarray) -> float:
    return float(np.percentile(values, CONSISTENCY_PERCENTILE))


def outcome_factor(row: pd.Series) -> float:
    if row.get("reopened_source") == "missing" or row.get("reopened") is None or pd.isna(row.get("reopened")):
        return 0.85  # no outcome data (Source A)
    if bool(row["reopened"]):
        return 0.5
    reas = row.get("no_of_reassignments")
    if reas is not None and not pd.isna(reas) and reas >= 5:
        return 0.75
    return 1.0


COMPLETENESS_FIELDS = ["impact", "urgency", "priority", "closure_code", "open_time", "resolved_time"]
PROVENANCE_FACTOR = {"original": 1.0, "synthetic": 0.8}


def score_record(row: pd.Series, consistency_flag: bool) -> QualityResult:
    detail, flags = resolution_detail(row.get("resolution_notes"))
    complete = float(np.mean([row.get(f"{f}_source", "missing") != "missing" for f in COMPLETENESS_FIELDS]))
    contradictions = 0
    if bool(row.get("category_conflict")):
        flags.append("category_text_conflict")
        contradictions += 1
    if closure_note_conflict(row.get("closure_class"), row.get("resolution_notes")):
        flags.append("closure_note_conflict")
        contradictions += 1
    if consistency_flag:
        flags.append("resolution_inconsistent_with_similar")
        contradictions += 1
    if row.get("priority_consistent") is False:
        flags.append("priority_matrix_inconsistent")
        contradictions += 1
    consistency = max(0.0, 1.0 - 0.5 * contradictions)
    outcome = outcome_factor(row)
    if outcome == 0.5:
        flags.append("reopened_after_fix")
    elif outcome == 0.75:
        flags.append("high_reassignments")
    score = 0.5 * detail + 0.15 * complete + 0.2 * consistency + 0.15 * outcome
    tier = "high" if score >= 0.7 else ("medium" if score >= 0.5 else "low")
    return QualityResult(round(float(score), 4), tier, flags, {
        "resolution_detail": detail, "completeness": round(complete, 3),
        "consistency": consistency, "outcome": outcome,
    })


def assess(kb: pd.DataFrame, desc_emb: np.ndarray, res_emb: np.ndarray, doc_emb: np.ndarray,
           near_dup_threshold: float = 0.95) -> tuple[pd.DataFrame, dict]:
    """Assess all KB records. Returns (per-record quality frame, run metadata).

    `desc_emb` / `res_emb` must be embeddings of the entity-masked texts (see mask_entities)."""
    kb = kb.reset_index(drop=True)
    dup = exact_duplicate_groups(kb)
    near = near_duplicate_groups(kb["incident_id"].tolist(), doc_emb, near_dup_threshold)
    detail_ok = np.array([resolution_detail(n)[0] > 0.2 for n in kb["resolution_notes"]])
    cons = resolution_consistency(desc_emb, res_emb, dup.tolist(), detail_ok)
    fence = low_fence(cons[detail_ok])
    rows = []
    for i, r in kb.iterrows():
        res = score_record(r, consistency_flag=bool(detail_ok[i] and cons[i] < fence))
        canonical = dup[i] == r["incident_id"]
        if not canonical:
            res.flags.append("exact_duplicate")
        elif near[i] != r["incident_id"] and dup[i] == r["incident_id"]:
            res.flags.append("near_duplicate")
        text_src = r.get("resolution_notes_source", "original")
        rows.append({
            "incident_id": r["incident_id"], "quality_score": res.score, "quality_tier": res.tier,
            "quality_flags": res.flags, "quality_components": res.components,
            "dup_group": dup[i], "near_dup_group": near[i], "canonical": bool(canonical),
            "resolution_consistency": round(float(cons[i]), 4),
            "influence_weight": round(res.score * PROVENANCE_FACTOR.get(text_src, 0.8), 4),
        })
    meta = {"resolution_consistency_fence": round(fence, 4), "near_dup_threshold": near_dup_threshold}
    return pd.DataFrame(rows), meta


def assess_single(row: pd.Series, desc_vec: np.ndarray, res_vec: np.ndarray,
                  neighbour_res: np.ndarray, fence: float) -> QualityResult:
    """Re-score one new record (KB evolution) against its nearest existing neighbours."""
    detail, _ = resolution_detail(row.get("resolution_notes"))
    cons = float(np.max(neighbour_res @ res_vec)) if len(neighbour_res) else 1.0
    res = score_record(row, consistency_flag=detail > 0.2 and cons < fence)
    res.components["resolution_consistency"] = round(cons, 4)
    return res
