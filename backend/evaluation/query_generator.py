"""Internal synthetic query generator (not a user-facing feature).

Builds a repeatable, labelled evaluation set:
  * KNOWN queries — natural-language rewrites of held-out historical incidents (lay, vague or
    technical style). The rewrite removes CI names, service names and root-cause wording so the
    query cannot trivially match its source text. Relevance labels come from the generator's
    ground-truth scenario (`gt_scenario`), never from the retrieval system itself.
  * NOVEL queries — the seeded "no historical match" probes (data/evaluation/novel_probes.jsonl).

Rewrites are produced by an LLM when one is available (cached to data/evaluation/eval_queries.jsonl
so the set is reproducible without a GPU), otherwise by a deterministic rule-based paraphraser.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from backend.data_pipeline.scenarios import SCENARIOS

CI_RE = re.compile(r"\b[A-Z]{2,4}\d{5,6}\b")
LAY = [
    (r"\bslow(er)?\b", "really slow"), (r"\bfreez\w*", "gets stuck"), (r"\btime[sd]? ?out\w*", "keeps loading and then fails"),
    (r"\berror\b", "strange message"), (r"\bcannot\b", "can't"), (r"\bunavailable\b", "not working"),
    (r"\bauthentication\b", "logging in"), (r"\bintermittently\b", "sometimes"), (r"\bdegrad\w*", "worse"),
]
STYLES = ["lay", "vague", "technical"]

STYLE_PROMPTS = {
    "lay": "Rewrite this incident as a short message (max 25 words) an employee would type into a help-desk chat. "
           "Use everyday words. Do not mention server names, product names or the root cause.",
    "vague": "Rewrite this incident as a very short, vague complaint (max 12 words) from a non-technical user. "
             "Do not mention server names, product names or the root cause.",
    "technical": "Rewrite this incident as a one-sentence technical symptom report (max 30 words) from a support "
                 "engineer. Describe symptoms only; do not state the root cause or the fix; no server names.",
}


def _service_names() -> list[str]:
    return sorted({s for sc in SCENARIOS for s in sc.services}, key=len, reverse=True)


def rule_rewrite(desc: str, style: str, rng: np.random.Generator) -> str:
    t = CI_RE.sub("the server", desc)
    for s in _service_names():
        t = re.sub(re.escape(s), "the system", t, flags=re.I)
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", t) if x.strip()]
    t = sents[0] if sents else t
    if style in ("lay", "vague"):
        for pat, rep in LAY:
            t = re.sub(pat, rep, t, flags=re.I)
    if style == "vague":
        t = " ".join(t.split()[:10])
    return t


def select_known(kb: pd.DataFrame, per_family: int, seed: int) -> pd.DataFrame:
    """Stratified by ground-truth scenario; only incidents with a usable description."""
    rng = np.random.default_rng(seed)
    kb = kb[kb["gt_scenario"].notna() & kb["canonical"].astype(bool)]
    parts = []
    for _, g in kb.groupby("gt_scenario"):
        n = min(per_family, len(g))
        parts.append(g.iloc[rng.choice(len(g), size=n, replace=False)])
    return pd.concat(parts).reset_index(drop=True)


def build_eval_set(kb: pd.DataFrame, novel_path: Path, out_path: Path, per_family: int = 10, seed: int = 42,
                   llm_generator=None) -> pd.DataFrame:
    """Create (or load) the labelled query set. Split 50/50 into validation / test per class."""
    if out_path.exists():
        return pd.read_json(out_path, lines=True)
    rng = np.random.default_rng(seed)
    known = select_known(kb, per_family, seed)
    styles = [STYLES[i % 3] for i in range(len(known))]
    rng.shuffle(styles)
    sources = [f"{t}. {d}" for t, d in zip(known["title"], known["description"])]
    if llm_generator is not None:
        prompts = [f"{STYLE_PROMPTS[s]}\n\nIncident: {CI_RE.sub('the server', src)}\n\nRewritten:" for s, src in zip(styles, sources)]
        outs = []
        for i in range(0, len(prompts), 48):
            outs += llm_generator.generate(prompts[i:i + 48], max_new_tokens=60,
                                           system="You rewrite IT incident reports. Answer with the rewritten text only.",
                                           temperature=0.8)
        queries = [o.strip().strip('"').split("\n")[0] for o in outs]
        gen = f"llm:{llm_generator.model_id}"
    else:
        queries = [rule_rewrite(d, s, rng) for d, s in zip(known["description"], styles)]
        gen = "rule-paraphraser-v1"
    rows = []
    for i, (r, q, st) in enumerate(zip(known.to_dict(orient="records"), queries, styles)):
        rows.append({"query_id": f"Q{i + 1:04d}", "query": q, "style": st, "label": "known",
                     "source_incident": r["incident_id"], "gt_scenario": r["gt_scenario"],
                     "gt_strategy": r.get("gt_strategy"), "generator": gen})
    probes = [json.loads(l) for l in novel_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for p in probes:
        rows.append({"query_id": p["probe_id"], "query": p["text"], "style": "hard" if p["hard"] else "novel",
                     "label": "novel", "source_incident": None, "gt_scenario": None, "gt_strategy": None,
                     "generator": "seeded probe"})
    df = pd.DataFrame(rows)
    df["split"] = "test"
    for _, g in df.groupby(["label", "style"]):  # stratified so hard probes land in both splits
        idx = g.index.to_numpy()
        rng.shuffle(idx)
        df.loc[idx[: len(idx) // 2], "split"] = "validation"
    df.to_json(out_path, orient="records", lines=True)
    return df
