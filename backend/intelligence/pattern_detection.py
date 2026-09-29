"""Incident Pattern Intelligence Engine.

One engine (presented as one feature) that combines:
  * fingerprint-based clustering into incident families
    (semantic similarity + resolution similarity + fingerprint fields — not text alone)
  * cross-symptom root-cause discovery (different symptoms, one dominant root cause)
  * recurrence / proactive "potential pattern requiring investigation" findings (recurrence.py)
  * the relationship graph (graph.py) and causal chains (causal_chain.py)

Family matching for a new incident uses the retrieval evidence (which families the relevant
historical incidents belong to) plus centroid similarity — both real computed numbers.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score

from backend.config.settings import Settings, get_settings
from backend.intelligence.fingerprinting import FIELDS, UNKNOWN, Fingerprint

log = logging.getLogger(__name__)

# Feature-block weights (design choice, fixed a priori — not tuned on ground truth).
W_DESC, W_RES = 1.0, 0.8
W_FP = {"root_cause": 0.9, "component": 0.5, "symptom": 0.4, "failure_type": 0.3}
MIN_FAMILY_SIZE = 3


# ------------------------------------------------------------------ features

def fingerprint_onehot(fps: list[Fingerprint]) -> tuple[np.ndarray, list[str]]:
    blocks, names = [], []
    for fld, w in W_FP.items():
        vocab = sorted({fp.values[fld] for fp in fps if fp.values[fld] != UNKNOWN})
        idx = {v: i for i, v in enumerate(vocab)}
        m = np.zeros((len(fps), max(1, len(vocab))), dtype=np.float32)
        for r, fp in enumerate(fps):
            v = fp.values[fld]
            if v in idx:
                m[r, idx[v]] = 1.0
        blocks.append(m * w)
        names += [f"{fld}={v}" for v in vocab] or [f"{fld}=<none>"]
    return np.hstack(blocks), names


def feature_matrix(desc_emb: np.ndarray, res_emb: np.ndarray, fps: list[Fingerprint],
                   usable_res: np.ndarray, use_fingerprint: bool = True, use_resolution: bool = True) -> np.ndarray:
    parts = [W_DESC * desc_emb]
    if use_resolution:
        parts.append(W_RES * res_emb * usable_res[:, None])  # generic notes carry no strategy signal
    if use_fingerprint:
        parts.append(fingerprint_onehot(fps)[0])
    X = np.hstack(parts).astype(np.float32)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)


def choose_clusters(X: np.ndarray, k_range=range(12, 62, 2), seed: int = 42) -> tuple[np.ndarray, int, dict]:
    """Pick the number of families by silhouette (cosine) — no ground-truth labels involved."""
    rng = np.random.default_rng(seed)
    sample = rng.choice(len(X), size=min(len(X), 2500), replace=False)
    best, sweep = None, {}
    for k in k_range:
        labels = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average").fit_predict(X)
        sil = float(silhouette_score(X[sample], labels[sample], metric="cosine"))
        sweep[k] = round(sil, 4)
        if best is None or sil > best[0]:
            best = (sil, k, labels)
    return best[2], best[1], sweep


# ------------------------------------------------------------------ family model

@dataclass
class Family:
    family_id: str
    name: str
    members: list[str]
    signature: dict[str, dict[str, float]]
    centroid: np.ndarray
    status: str = "active"
    members_original_text: int = 0
    members_synthetic_text: int = 0
    cross_symptom: dict | None = None
    extra: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"family_id": self.family_id, "name": self.name, "size": len(self.members), "status": self.status,
                "members_original_text": self.members_original_text,
                "members_synthetic_text": self.members_synthetic_text,
                "signature": self.signature, "cross_symptom": self.cross_symptom}


def signature_of(fps: list[Fingerprint]) -> dict[str, dict[str, float]]:
    sig = {}
    for fld in FIELDS:
        if fld in ("business_impact", "service"):
            continue
        c = Counter(fp.values[fld] for fp in fps)
        n = len(fps)
        sig[fld] = {v: round(k / n, 3) for v, k in c.most_common(4)}
    return sig


def dominant(sig: dict, fld: str) -> tuple[str, float]:
    for v, share in sig.get(fld, {}).items():
        if v != UNKNOWN:
            return v, share
    return UNKNOWN, 0.0


def family_name(sig: dict) -> str:
    comp, _ = dominant(sig, "component")
    sym, _ = dominant(sig, "symptom")
    rc, _ = dominant(sig, "root_cause")
    parts = [p for p in (comp, sym) if p != UNKNOWN]
    head = " · ".join(parts) if parts else "Mixed incidents"
    return f"{head} — {rc}" if rc != UNKNOWN else head


def cross_symptom_finding(fps: list[Fingerprint]) -> dict | None:
    """Different symptoms, one dominant root cause → cross-symptom root-cause discovery."""
    n = len(fps)
    rc, rc_share = Counter(fp.values["root_cause"] for fp in fps).most_common(1)[0]
    if rc == UNKNOWN or rc_share / n < 0.6:
        return None
    sym = Counter(fp.values["symptom"] for fp in fps if fp.values["root_cause"] == rc and fp.values["symptom"] != UNKNOWN)
    distinct = {s: c for s, c in sym.items() if c / n >= 0.1}
    if len(distinct) < 2:
        return None
    return {"root_cause": rc, "root_cause_share": round(rc_share / n, 3),
            "symptoms": {s: round(c / n, 3) for s, c in sorted(distinct.items(), key=lambda t: -t[1])},
            "finding": f"{len(distinct)} different symptom presentations share the root cause '{rc}'"}


def build_families(ids: list[str], records: pd.DataFrame, desc_emb: np.ndarray, X: np.ndarray,
                   labels: np.ndarray, fps: list[Fingerprint]) -> tuple[list[Family], dict[str, str]]:
    rec = records.set_index("incident_id")
    families, assign = [], {}
    order = sorted(set(labels), key=lambda l: -(labels == l).sum())
    fid_n = 0
    noise_members = []
    for lab in order:
        idx = np.where(labels == lab)[0]
        if len(idx) < MIN_FAMILY_SIZE:
            noise_members += idx.tolist()
            continue
        fid_n += 1
        fid = f"F{fid_n:03d}"
        m_fps = [fps[i] for i in idx]
        sig = signature_of(m_fps)
        members = [ids[i] for i in idx]
        c = desc_emb[idx].mean(0)
        srcs = rec.loc[members, "description_source"]
        fam = Family(fid, family_name(sig), members, sig, c / np.linalg.norm(c),
                     members_original_text=int((srcs == "original").sum()),
                     members_synthetic_text=int((srcs == "synthetic").sum()),
                     cross_symptom=cross_symptom_finding(m_fps))
        families.append(fam)
        for m in members:
            assign[m] = fid
    # tiny clusters: attach to the nearest family if clearly similar, else keep as "emerging"
    if families:
        cents = np.vstack([f.centroid for f in families])
        for i in noise_members:
            sims = cents @ desc_emb[i]
            j = int(np.argmax(sims))
            if sims[j] >= 0.5:
                families[j].members.append(ids[i])
                assign[ids[i]] = families[j].family_id
            else:
                fid_n += 1
                fid = f"F{fid_n:03d}"
                sig = signature_of([fps[i]])
                fam = Family(fid, family_name(sig), [ids[i]], sig, desc_emb[i].copy(), status="emerging",
                             members_original_text=int(rec.at[ids[i], "description_source"] == "original"),
                             members_synthetic_text=int(rec.at[ids[i], "description_source"] == "synthetic"))
                families.append(fam)
                assign[ids[i]] = fid
    return families, assign


# ------------------------------------------------------------------ runtime engine

class PatternEngine:
    """Runtime view over the families built offline (scripts/build_intelligence.py)."""

    def __init__(self, families: list[Family], assign: dict[str, str], fingerprints: dict[str, dict],
                 meta: dict, embedder=None):
        self.families = {f.family_id: f for f in families}
        self.assign = assign
        self.fingerprints = fingerprints
        self.meta = meta
        self.embedder = embedder
        self._refresh_centroids()

    def _refresh_centroids(self) -> None:
        self._fids = list(self.families)
        self._cents = np.vstack([self.families[f].centroid for f in self._fids]) if self._fids else np.zeros((0, 384))

    # ---------------------------------------------------------------- persistence
    @staticmethod
    def artifact_path(s: Settings) -> Path:
        return Path(s.processed_dir) / "patterns.json"

    def save(self, s: Settings) -> None:
        payload = {
            "meta": self.meta, "assign": self.assign,
            "families": [{**f.summary(), "members": f.members, "centroid": f.centroid.round(6).tolist(),
                          "extra": f.extra} for f in self.families.values()],
        }
        self.artifact_path(s).write_text(json.dumps(payload), encoding="utf-8")
        fp_path = Path(s.processed_dir) / "fingerprints.json"
        fp_path.write_text(json.dumps(self.fingerprints), encoding="utf-8")

    @classmethod
    def load(cls, s: Settings | None = None, store=None, embedder=None) -> "PatternEngine":
        s = s or get_settings()
        data = json.loads(cls.artifact_path(s).read_text(encoding="utf-8"))
        fams = [Family(f["family_id"], f["name"], f["members"], f["signature"], np.asarray(f["centroid"], dtype=np.float32),
                       status=f["status"], members_original_text=f["members_original_text"],
                       members_synthetic_text=f["members_synthetic_text"], cross_symptom=f.get("cross_symptom"),
                       extra=f.get("extra", {})) for f in data["families"]]
        fps = json.loads((Path(s.processed_dir) / "fingerprints.json").read_text(encoding="utf-8"))
        return cls(fams, data["assign"], fps, data["meta"], embedder)

    # ---------------------------------------------------------------- queries
    def family_of(self, incident_id: str) -> Family | None:
        fid = self.assign.get(incident_id)
        return self.families.get(fid) if fid else None

    def fingerprint_of(self, incident_id: str) -> Fingerprint | None:
        d = self.fingerprints.get(incident_id)
        return Fingerprint.from_dict(d) if d else None

    def centroid_similarities(self, q_emb: np.ndarray) -> dict[str, float]:
        if not len(self._fids):
            return {}
        sims = self._cents @ q_emb
        return {f: float(s) for f, s in zip(self._fids, sims)}

    def match(self, retrieved: list, q_emb: np.ndarray | None) -> list[dict]:
        """Rank families for a new incident.

        vote_share      — share of the retrieval evidence mass (relevance confidence × influence
                          weight) that falls in the family
        max_relevance   — best relevance confidence among the family's retrieved members
        centroid_sim    — cosine between the query and the family's symptom centroid
        match_strength  — vote_share × max_relevance (both real; no LLM involvement)
        """
        mass: dict[str, float] = {}
        best: dict[str, float] = {}
        ids: dict[str, list[str]] = {}
        total = 0.0
        for r in retrieved:
            fid = self.assign.get(r.incident_id)
            if not fid:
                continue
            conf = r.scores.relevance_confidence
            w = (conf if conf is not None else 0.5) * max(0.05, r.quality.get("influence_weight", 0.5))
            mass[fid] = mass.get(fid, 0.0) + w
            best[fid] = max(best.get(fid, 0.0), conf if conf is not None else 0.0)
            ids.setdefault(fid, []).append(r.incident_id)
            total += w
        cents = self.centroid_similarities(q_emb) if q_emb is not None else {}
        out = []
        for fid in set(mass) | set(sorted(cents, key=lambda f: -cents[f])[:3]):
            fam = self.families[fid]
            vote = mass.get(fid, 0.0) / total if total else 0.0
            has_conf = any(r.scores.relevance_confidence is not None for r in retrieved)
            out.append({
                "family_id": fid, "name": fam.name, "size": len(fam.members), "status": fam.status,
                "vote_share": round(vote, 4),
                "max_relevance": round(best.get(fid, 0.0), 4) if has_conf else None,
                "centroid_similarity": round(cents.get(fid, 0.0), 4) if cents else None,
                "match_strength": round(vote * best.get(fid, 0.0), 4) if has_conf else None,
                "supporting_incidents": ids.get(fid, []),
                "signature": fam.signature,
            })
        key = (lambda d: (d["match_strength"] or 0.0, d["vote_share"])) if out and out[0]["match_strength"] is not None \
            else (lambda d: (d["vote_share"], d["centroid_similarity"] or 0.0))
        return sorted(out, key=key, reverse=True)

    def assign_new(self, incident_id: str, desc_emb: np.ndarray, fp: Fingerprint, threshold: float = 0.55) -> tuple[str, bool, float]:
        """KB evolution: attach a new record to the nearest family or spawn an 'emerging' one."""
        sims = self._cents @ desc_emb if len(self._fids) else np.zeros(0)
        if len(sims) and float(sims.max()) >= threshold:
            fid = self._fids[int(np.argmax(sims))]
            fam = self.families[fid]
            fam.members.append(incident_id)
            n = len(fam.members)
            c = fam.centroid * (n - 1) / n + desc_emb / n
            fam.centroid = c / np.linalg.norm(c)
            created, sim = False, float(sims.max())
        else:
            fid = f"F{len(self.families) + 1:03d}"
            while fid in self.families:
                fid = f"F{int(fid[1:]) + 1:03d}"
            sig = signature_of([fp])
            self.families[fid] = Family(fid, family_name(sig), [incident_id], sig, desc_emb.copy(), status="emerging")
            created, sim = True, float(sims.max()) if len(sims) else 0.0
        self.assign[incident_id] = fid
        self.fingerprints[incident_id] = fp.as_dict()
        self._refresh_centroids()
        return fid, created, sim
