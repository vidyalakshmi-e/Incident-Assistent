"""Incident triage: classification, priority/impact/urgency, routing, L1→L2→L3 tier, resolution-time
prediction and fix-accuracy assessment.

Models (trained by scripts/train_models.py, evaluated in Phase 9):
  * text classifiers (TF-IDF + logistic regression) for category / priority / impact / urgency —
    used when the structured field is not supplied. Labels are real (Source B fields; Source A
    category is the derived corrected category). Caveat: Source B text is synthetic and was
    conditioned on these fields, so text-classifier accuracy is optimistic.
  * resolution-time regressor (gradient boosting on log hours) — trained on ~44k real rows using
    only fields known when an incident is opened; time-based train/test split
  * fix-accuracy model P(reopen) — trained on real Reopen_Time labels with fields known at
    resolution time (closure code, reassignments, resolution time, CI, priority)
"""
from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from backend.config.settings import Settings, get_settings
from backend.config.taxonomy import CATEGORY_TEAM, CI_GROUP_TEAM

OPEN_FEATURES = ["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type", "open_hour",
                 "open_weekday"]
RESOLVE_FEATURES = ["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type", "closure_class",
                    "log_resolution_hours", "no_of_reassignments"]
COMPONENT_TEAM = {
    "Database": "Database Administration", "Authentication service": "Identity & Access Management",
    "VPN gateway": "Network Operations", "Network": "Network Operations", "Storage": "Storage Engineering",
    "End-user device": "Workplace Hardware", "Printer": "Workplace Hardware", "Banking device": "Branch Devices",
    "Citrix / VDI": "Workplace Virtualization", "Mail (Exchange/Outlook)": "Messaging & Collaboration",
    "SAP": "SAP Competence Center", "TLS certificate": "Security Operations (PKI)",
    "Endpoint security": "Security Operations", "Batch / interface": "Application Support (batch)",
    "Server": "Server Operations", "Media platform": "Media Platform Operations", "Application": "Application Support",
}
FAILURE_EXPERTISE = {
    "performance degradation": "performance", "resource exhaustion": "capacity", "hard failure": "availability",
    "intermittent failure": "stability", "data integrity": "data", "security event": "security response",
    "functional failure": "functional defects", "no technical fault": "functional / user support",
}


def open_frame(df: pd.DataFrame) -> pd.DataFrame:
    t = pd.to_datetime(df["open_time"])
    out = df.reindex(columns=["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type"]).astype(str)
    out["open_hour"] = t.dt.hour.fillna(-1).astype(int)
    out["open_weekday"] = t.dt.weekday.fillna(-1).astype(int)
    return out


def resolve_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reindex(columns=["ci_group", "ci_subcategory", "impact", "urgency", "priority", "ticket_type",
                              "closure_class"]).astype(str)
    out["log_resolution_hours"] = np.log1p(df["resolution_hours"].clip(lower=0).fillna(0).to_numpy())
    out["no_of_reassignments"] = df["no_of_reassignments"].fillna(0).to_numpy()
    return out


@dataclass
class OutcomeModels:
    bundle: dict | None

    @classmethod
    def load(cls, s: Settings | None = None) -> "OutcomeModels":
        s = s or get_settings()
        p = Path(s.processed_dir) / "models.pkl"
        if not p.exists():
            return cls(None)
        with p.open("rb") as fh:
            return cls(pickle.load(fh))

    @property
    def available(self) -> bool:
        return self.bundle is not None

    # ---------------------------------------------------------------- text classifiers
    def classify_text(self, text: str) -> dict:
        if not self.available:
            return {}
        out = {}
        for name, clf in self.bundle["text_classifiers"].items():
            proba = clf.predict_proba([text])[0]
            i = int(np.argmax(proba))
            out[name] = {"value": str(clf.classes_[i]), "probability": round(float(proba[i]), 4),
                         "distribution": {str(c): round(float(p), 3) for c, p in zip(clf.classes_, proba)},
                         "provenance": "derived (text classifier)"}
        return out

    # ---------------------------------------------------------------- resolution time
    def predict_resolution_hours(self, fields: dict) -> dict | None:
        if not self.available:
            return None
        row = pd.DataFrame([{**{k: fields.get(k, "Unknown") for k in ["ci_group", "ci_subcategory", "impact",
                                                                        "urgency", "priority", "ticket_type"]},
                             "open_time": fields.get("open_time") or datetime.utcnow()}])
        X = open_frame(row)
        m = self.bundle["resolution_time"]
        enc = m["encoder"].transform(X[OPEN_FEATURES])
        med = float(np.expm1(m["median"].predict(enc)[0]))
        lo = float(np.expm1(m["q25"].predict(enc)[0]))
        hi = float(np.expm1(m["q75"].predict(enc)[0]))
        return {"predicted_hours_median": round(max(med, 0), 2), "interval_p25_p75": [round(max(lo, 0), 2), round(max(hi, 0), 2)],
                "model": "HistGradientBoosting on log1p(hours) (+ quantile models)",
                "test_metrics": m.get("test_metrics"), "features_used": {k: str(X.iloc[0][k]) for k in OPEN_FEATURES}}

    # ---------------------------------------------------------------- fix accuracy
    def reopen_risk(self, fields: dict) -> dict | None:
        if not self.available:
            return None
        row = pd.DataFrame([{k: fields.get(k, "Unknown") for k in ["ci_group", "ci_subcategory", "impact", "urgency",
                                                                   "priority", "ticket_type", "closure_class"]}
                            | {"resolution_hours": fields.get("resolution_hours", 1.0),
                               "no_of_reassignments": fields.get("no_of_reassignments", 0)}])
        X = resolve_frame(row)
        m = self.bundle["fix_accuracy"]
        p = float(m["model"].predict_proba(m["encoder"].transform(X[RESOLVE_FEATURES]))[0, 1])
        return {"p_reopen": round(p, 4), "first_time_fix_probability": round(1 - p, 4),
                "base_rate": m.get("base_rate"), "model": "HistGradientBoosting classifier on real Reopen_Time labels",
                "test_metrics": m.get("test_metrics")}


# -------------------------------------------------------------------- routing / tiers

def route_team(fp_values: dict, ci_group: str | None = None, category: str | None = None) -> dict:
    comp = fp_values.get("component", "Unknown")
    team = COMPONENT_TEAM.get(comp) or (CI_GROUP_TEAM.get(ci_group) if ci_group else None) or \
        (CATEGORY_TEAM.get(category) if category else None) or "Service Desk"
    exp = FAILURE_EXPERTISE.get(fp_values.get("failure_type", "Unknown"))
    expertise = f"{comp} {exp}".strip() if comp != "Unknown" and exp else (comp if comp != "Unknown" else None)
    return {"team": team, "expertise": expertise,
            "basis": "derived from the fingerprint's component and failure type (no assignment-group data exists in "
                     "the source, so no individual-level expertise is claimed)"}


def route_tier(tiers: list[str], *, priority: str | None, novel: bool | None, destructive: bool = False,
               troubleshooting_exhausted: bool = False, family_mean_reassignments: float | None = None,
               family_reopen_rate: float | None = None) -> dict:
    """Configurable tier order (settings.escalation_tiers, default "L1,L2,L3")."""
    idx, reasons = 0, []
    if priority in {"1", "2"}:
        idx += 1
        reasons.append(f"priority {priority} (critical/high)")
    if novel:
        idx += 1
        reasons.append("novel incident — no historical playbook")
    if destructive:
        idx += 1
        reasons.append("recommended action is destructive — needs specialist confirmation")
    if troubleshooting_exhausted:
        idx += 1
        reasons.append("guided troubleshooting exhausted without resolution")
    if family_mean_reassignments is not None and family_mean_reassignments >= 2.0:
        idx += 1
        reasons.append(f"historically this pattern needed {family_mean_reassignments:.1f} reassignments on average")
    if family_reopen_rate is not None and family_reopen_rate >= 0.15 and troubleshooting_exhausted:
        idx += 1
        reasons.append(f"historical reopen rate for this pattern {family_reopen_rate:.0%}")
    idx = min(idx, len(tiers) - 1)
    return {"tier": tiers[idx], "tier_order": tiers, "reasons": reasons or ["no escalation criteria met — first line"]}


def family_outcome_stats(store, family) -> dict:
    """Real outcome statistics of a family's members (only members with real outcome fields)."""
    if family is None:
        return {}
    rows = [store.get(m) for m in family.members if store.get(m)]
    with_out = [r for r in rows if r.get("reopened_source") != "missing" and r.get("reopened") is not None]
    if len(with_out) < 20:
        return {"n_with_outcome": len(with_out), "stats_supported": False}
    reop = np.mean([bool(r["reopened"]) for r in with_out])
    reas = np.mean([float(r.get("no_of_reassignments") or 0) for r in with_out])
    hrs = [float(r["resolution_hours"]) for r in with_out if r.get("resolution_hours") is not None and not pd.isna(r["resolution_hours"])]
    return {"n_with_outcome": len(with_out), "stats_supported": True, "reopen_rate": round(float(reop), 4),
            "first_time_fix_rate": round(1 - float(reop), 4), "mean_reassignments": round(float(reas), 2),
            "median_resolution_hours": round(float(np.median(hrs)), 2) if hrs else None}


def save_models(bundle: dict, s: Settings | None = None) -> None:
    s = s or get_settings()
    with (Path(s.processed_dir) / "models.pkl").open("wb") as fh:
        pickle.dump(bundle, fh)
    meta = {k: v.get("test_metrics") for k, v in bundle.items() if isinstance(v, dict) and "test_metrics" in v}
    meta["text_classifiers"] = bundle.get("text_classifier_metrics")
    (Path(s.evaluation_dir) / "model_metrics.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


class FrameEncoder:
    """Ordinal-encode categorical columns (unknown -> -1) and pass numeric columns through."""

    def __init__(self, categorical: list[str], numeric: list[str]):
        from sklearn.preprocessing import OrdinalEncoder

        self.categorical, self.numeric = categorical, numeric
        self.enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1)

    def fit(self, X: pd.DataFrame) -> "FrameEncoder":
        self.enc.fit(X[self.categorical].astype(str))
        return self

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        cat = self.enc.transform(X[self.categorical].astype(str))
        num = X[self.numeric].to_numpy(dtype=float) if self.numeric else np.zeros((len(X), 0))
        return np.hstack([cat, num])

    @property
    def categorical_mask(self) -> list[bool]:
        return [True] * len(self.categorical) + [False] * len(self.numeric)
