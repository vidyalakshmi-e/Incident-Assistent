"""Recurrence detection and proactive prevention findings.

Findings are always framed as "potential pattern requiring investigation", never as a certain
prediction (PROACTIVE PREVENTION). Recurrence is computed only where timestamps exist.
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

REPEAT_WINDOW_DAYS = 30
HOTSPOT_WINDOW_DAYS = 14


def family_recurrence(members: pd.DataFrame) -> dict:
    """Frequency / time distribution for one family (members with real Open_Time only)."""
    timed = members[members["open_time"].notna()].sort_values("open_time")
    out: dict = {"members": int(len(members)), "members_with_timestamps": int(len(timed)),
                 "provenance_note": "timestamps are original; family membership is derived from the incident text "
                                    "(synthetic for Source B rows)"}
    if len(timed) < 3:
        out["status"] = "insufficient temporal data"
        return out
    ts = pd.to_datetime(timed["open_time"])
    monthly = ts.dt.to_period("M").value_counts().sort_index()
    gaps = ts.diff().dt.total_seconds().dropna() / 86400
    repeats = []
    for ci, g in timed.groupby("ci_name"):
        t = pd.to_datetime(g["open_time"]).sort_values()
        close = int((t.diff().dt.total_seconds() / 86400 <= REPEAT_WINDOW_DAYS).sum())
        if close >= 1:
            repeats.append({"ci_name": ci, "incidents": int(len(g)), "repeats_within_30d": close})
    repeats.sort(key=lambda r: (-r["repeats_within_30d"], -r["incidents"]))
    out.update({
        "status": "ok",
        "first_seen": str(ts.min()), "last_seen": str(ts.max()),
        "monthly_counts": {str(k): int(v) for k, v in monthly.items()},
        "median_days_between": round(float(np.median(gaps)), 2) if len(gaps) else None,
        "recurring_cis": repeats[:10],
        "reopen_rate": round(float(timed["reopened"].astype(float).mean()), 4) if "reopened" in timed else None,
    })
    if repeats:
        top = repeats[0]
        out["finding"] = (f"Potential pattern requiring investigation: CI {top['ci_name']} had "
                          f"{top['incidents']} incidents in this family, {top['repeats_within_30d']} of them within "
                          f"{REPEAT_WINDOW_DAYS} days of the previous one.")
    return out


def ci_hotspots(unified: pd.DataFrame, top_n: int = 15, min_incidents: int = 10) -> list[dict]:
    """Real-data proactive finding over *all* structured incidents: CIs with bursts of incidents in a
    14-day window. Uses only original fields (CI_Name, Open_Time, Closure_Code, CI_Subcat)."""
    df = unified[(unified["source"] == "B_event_log") & unified["open_time"].notna()][
        ["ci_name", "ci_subcategory", "open_time", "closure_code", "reopened", "priority"]].copy()
    df = df.sort_values("open_time")
    out = []
    for ci, g in df.groupby("ci_name"):
        if len(g) < min_incidents:
            continue
        t = g["open_time"].values.astype("datetime64[s]").astype(np.int64)
        win = HOTSPOT_WINDOW_DAYS * 86400
        j, best, best_i = 0, 0, 0
        for i in range(len(t)):
            while t[i] - t[j] > win:
                j += 1
            if i - j + 1 > best:
                best, best_i = i - j + 1, j
        if best >= min_incidents:
            w = g.iloc[best_i:best_i + best]
            cc = Counter(w["closure_code"]).most_common(2)
            out.append({
                "ci_name": ci, "ci_subcategory": g["ci_subcategory"].iloc[0], "total_incidents": int(len(g)),
                "max_in_14_days": int(best), "window_start": str(w["open_time"].iloc[0]),
                "top_closure_codes": {k: int(v) for k, v in cc},
                "reopen_rate": round(float(g["reopened"].astype(float).mean()), 3),
                "finding": f"Potential pattern requiring investigation: {best} incidents on {ci} within "
                           f"{HOTSPOT_WINDOW_DAYS} days (all fields original).",
            })
    out.sort(key=lambda r: -r["max_in_14_days"])
    return out[:top_n]


def family_transitions(records: pd.DataFrame, assign: dict[str, str], window_days: int = 14,
                       min_support: int = 5, min_lift: float = 2.0) -> dict:
    """Evolution / failure-chain candidates: family A followed by family B on the same CI within
    `window_days`, reported only when support and lift over independence are both high."""
    df = records[records["open_time"].notna()].copy()
    df["family"] = df["incident_id"].map(assign)
    df = df[df["family"].notna()].sort_values("open_time")
    pairs = Counter()
    for _, g in df.groupby("ci_name"):
        rows = g[["family", "open_time"]].values
        for i in range(len(rows) - 1):
            gap = (pd.Timestamp(rows[i + 1][1]) - pd.Timestamp(rows[i][1])).total_seconds() / 86400
            if gap <= window_days and rows[i][0] != rows[i + 1][0]:
                pairs[(rows[i][0], rows[i + 1][0])] += 1
    total = sum(pairs.values())
    fam_freq = df["family"].value_counts(normalize=True)
    chains = []
    for (a, b), n in pairs.items():
        expected = total * fam_freq.get(a, 0) * fam_freq.get(b, 0)
        lift = n / expected if expected else 0.0
        if n >= min_support and lift >= min_lift:
            chains.append({"from": a, "to": b, "support": n, "lift": round(lift, 2)})
    chains.sort(key=lambda c: (-c["lift"], -c["support"]))
    return {"window_days": window_days, "transitions_considered": total, "chains": chains[:20],
            "tag": "derived (timestamps and CIs original; family labels derived from text)",
            "note": "none met the support/lift thresholds" if not chains else ""}
