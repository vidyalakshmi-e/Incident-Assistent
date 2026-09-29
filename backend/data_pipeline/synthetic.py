"""Conditioned synthetic text generation for Source B rows (DATASET Step 4).

Two stages:
1. `plan_synthetic_rows` — picks a stratified sample of *real* Source B rows and, for each row,
   draws a scenario + strategy + wording "brief" conditioned on that row's real fields.
2. A verbalizer turns each brief into title / description / resolution_notes:
   * `TemplateVerbalizer` — deterministic conditioned grammar (always available)
   * `llm_verbalizer.LLMVerbalizer` — an LLM writes the text from the same brief
   Both record which generator produced the text (`text_generator`).

No row is invented here: every generated text is attached to an existing real incident, and all
structured fields of that incident stay untouched and tagged "original".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from backend.data_pipeline.scenarios import SCENARIO_BY_ID, SCENARIOS, Scenario, Strategy

TARGET_KB_ROWS = 3000
MIN_PER_SCENARIO = 40
MAX_PER_SCENARIO = 220

VIEW_WEIGHTS = {"user": 0.5, "monitoring": 0.25, "engineer": 0.25}

LOW_QUALITY_NOTES = [
    "closed", "fixed", "resolved", "done", "ok now", "solved", "issue resolved, closing ticket",
    "user confirmed, closed", "see previous call", "no further action", "works again", "restarted",
]

# Impact 4/5 are the dataset's default levels (84% of rows), so they are phrased cautiously.
SCOPE_BY_IMPACT = {
    "1": "All users across the organisation are affected.",
    "2": "Several departments are affected.",
    "3": "Our whole team is affected.",
    "4": "Some colleagues seem to have the same problem.",
    "5": "Only I seem to be affected.",
}
SCOPE_DEVICE = {
    "1": "Devices in several branches are affected.",
    "2": "Several devices at this location are affected.",
    "3": "More than one device here has the problem.",
    "4": "",
    "5": "",
}
SCOPE_MONITORING = {
    "1": "Impact: organisation-wide.", "2": "Impact: multiple departments.", "3": "Impact: one team.",
    "4": "Impact: a small group of users.", "5": "Impact: single user.",
}
URGENCY_PHRASE = {
    "1": "This is blocking customer transactions, please treat as urgent.",
    "2": "This is blocking customer transactions, please treat as urgent.",
    "3": "We can work around it for now but it is disruptive.",
}


@dataclass
class Brief:
    incident_id: str
    scenario_id: str
    strategy_id: str
    view: str
    service: str
    ci: str
    symptom_seed: str
    title_seed: str
    trigger: str  # "" when not mentioned
    scope_sentence: str
    urgency_sentence: str
    environment: str  # "" | "production" | "acceptance"
    root_cause: str
    strategy_label: str
    steps: list[str]
    note_seed: str
    note_quality: str  # "detailed" | "low"
    low_quality_note: str
    reassignments: int
    seeded_defect: str  # "" | "contradiction"

    def key(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ sampling


def _eligible_mask(df: pd.DataFrame, sc: Scenario) -> pd.Series:
    m = df["ci_group"].isin(sc.ci_groups) & df["closure_code"].isin(list(sc.closure_codes))
    if sc.ci_subcats:
        m &= df["ci_subcategory"].isin(sc.ci_subcats)
    return m


def allocate(df: pd.DataFrame, target: int = TARGET_KB_ROWS) -> dict[str, int]:
    """Rows per scenario ∝ sqrt(eligible population), clipped. sqrt keeps rare families usable
    without letting the dominant application families swamp the knowledge base."""
    elig = {sc.id: int(_eligible_mask(df, sc).sum()) for sc in SCENARIOS}
    w = {k: np.sqrt(v) for k, v in elig.items() if v > 0}
    total = sum(w.values())
    alloc = {}
    for k, wk in w.items():
        n = int(round(target * wk / total))
        alloc[k] = int(min(max(n, MIN_PER_SCENARIO), MAX_PER_SCENARIO, elig[k]))
    return alloc


def _pick_strategy(sc: Scenario, closure: str, reassign: int, rng: np.random.Generator) -> Strategy:
    weights = []
    for st in sc.strategies:
        w = st.closure_affinity.get(closure, 0.3)
        if st.reassign_bias == "low":
            w *= 2.0 if reassign == 0 else 0.6
        elif st.reassign_bias == "high":
            w *= 2.0 if reassign >= 3 else (1.0 if reassign >= 1 else 0.4)
        weights.append(w)
    p = np.array(weights) / sum(weights)
    return sc.strategies[rng.choice(len(sc.strategies), p=p)]


def plan_synthetic_rows(eligible: pd.DataFrame, seed: int = 42, target: int = TARGET_KB_ROWS) -> list[Brief]:
    """Choose real rows and build a conditioned brief for each."""
    rng = np.random.default_rng(seed)
    alloc = allocate(eligible, target)
    taken: set[str] = set()
    briefs: list[Brief] = []
    # scarce scenarios first so they are not starved by broad ones
    order = sorted(alloc, key=lambda k: _eligible_mask(eligible, SCENARIO_BY_ID[k]).sum())
    for sid in order:
        sc = SCENARIO_BY_ID[sid]
        pool = eligible[_eligible_mask(eligible, sc) & ~eligible["incident_id"].isin(taken)]
        if pool.empty:
            continue
        weights = pool["closure_code"].map(sc.closure_codes).astype(float).to_numpy()
        weights = weights * np.where(pool["related_change"].notna(), sc.change_affinity, 1.0)
        weights = weights / weights.sum()
        n = min(alloc[sid], len(pool))
        idx = rng.choice(len(pool), size=n, replace=False, p=weights)
        for _, row in pool.iloc[np.sort(idx)].iterrows():
            taken.add(row["incident_id"])
            briefs.append(_make_brief(row, sc, rng))
    _seed_contradictions(briefs, rng)
    return briefs


def _make_brief(row: pd.Series, sc: Scenario, rng: np.random.Generator) -> Brief:
    reassign = int(row["no_of_reassignments"]) if pd.notna(row["no_of_reassignments"]) else 0
    closure = row["closure_code"]
    st = _pick_strategy(sc, closure, reassign, rng)
    views = [v for v in sc.views if sc.views[v]]
    vw = np.array([VIEW_WEIGHTS.get(v, 0.2) for v in views])
    view = views[rng.choice(len(views), p=vw / vw.sum())]
    service = sc.services[rng.integers(len(sc.services))]
    ci = str(row["ci_name"])
    fmt = {"service": service, "ci": ci}
    trigger = sc.triggers[rng.integers(len(sc.triggers))]
    if trigger and rng.random() > 0.6:
        trigger = ""  # trigger exists but the reporter did not mention it
    impact = str(row["impact"])
    if view == "monitoring":
        scope = SCOPE_MONITORING.get(impact, "")
    else:
        scope = (SCOPE_DEVICE if sc.device_scope else SCOPE_BY_IMPACT).get(impact, "")
    urg = URGENCY_PHRASE.get(str(row["urgency"]), "")
    r = rng.random()
    env = "production" if r < 0.30 else ("acceptance" if r < 0.34 else "")
    if not sc.env_applicable:
        env = ""
    # note quality conditioned on the real closure code: vague closure codes → vaguer notes
    p_low = 0.22 if closure in {"Other", "Unknown"} else 0.05
    quality = "low" if rng.random() < p_low else "detailed"
    return Brief(
        incident_id=row["incident_id"], scenario_id=sc.id, strategy_id=st.id, view=view,
        service=service, ci=ci,
        symptom_seed=sc.views[view][rng.integers(len(sc.views[view]))].format(**fmt),
        title_seed=sc.titles[rng.integers(len(sc.titles))].format(**fmt),
        trigger=trigger, scope_sentence=scope if rng.random() < 0.7 else "",
        urgency_sentence=urg if rng.random() < 0.6 else "", environment=env,
        root_cause=sc.root_cause, strategy_label=st.label, steps=st.steps,
        note_seed=st.notes[rng.integers(len(st.notes))].format(**fmt),
        note_quality=quality,
        low_quality_note=LOW_QUALITY_NOTES[rng.integers(len(LOW_QUALITY_NOTES))],
        reassignments=reassign, seeded_defect="",
    )


def _seed_contradictions(briefs: list[Brief], rng: np.random.Generator, rate: float = 0.015) -> None:
    """Seed a small number of records whose resolution note belongs to a different family.

    Gives the Knowledge Quality Manager something real to catch (and to be evaluated on).
    """
    n = max(1, int(len(briefs) * rate))
    idx = rng.choice(len(briefs), size=n, replace=False)
    for i in idx:
        b = briefs[i]
        other = [s for s in SCENARIOS if s.id != b.scenario_id and s.component != SCENARIO_BY_ID[b.scenario_id].component]
        sc = other[rng.integers(len(other))]
        st = sc.strategies[rng.integers(len(sc.strategies))]
        b.note_seed = st.notes[rng.integers(len(st.notes))].format(service=b.service, ci=b.ci)
        b.note_quality = "detailed"
        b.seeded_defect = "contradiction"


# ------------------------------------------------------------------ verbalizers


class TemplateVerbalizer:
    """Deterministic conditioned grammar. Used when no LLM is configured."""

    name = "template-grammar-v1"

    def render(self, b: Brief) -> dict[str, str]:
        parts = [b.symptom_seed]
        if b.trigger:
            parts.append(f"It started {b.trigger}.")
        if b.scope_sentence:
            parts.append(b.scope_sentence)
        if b.urgency_sentence:
            parts.append(b.urgency_sentence)
        if b.environment == "production":
            parts.append("This is in production.")
        elif b.environment == "acceptance":
            parts.append("Seen in the acceptance environment.")
        notes = b.low_quality_note if b.note_quality == "low" else b.note_seed
        if b.note_quality != "low" and b.reassignments >= 3:
            notes = f"Ticket passed through {b.reassignments} reassignments. " + notes
        return {"title": b.title_seed, "description": " ".join(parts), "resolution_notes": notes}
