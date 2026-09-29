"""Relationship graph.

Incident-level edges (persisted in SQL `incident_relationships`) come from real links:
  same_ci         observed — two incidents on the same configuration item (consecutive in time)
  repeat_same_ci  observed — same CI, next incident within 7 days
  same_kb_article observed — both tickets reference the same knowledge article (KB_number)
  same_change     observed — both linked to the same change record
  near_duplicate  derived  — embedding similarity ≥ 0.95 (Quality Manager)
Family-level graph (for the Pattern Explorer): families ↔ root causes / components, and
family ↔ family when they share a dominant root cause (derived) or CIs (observed).
"""
from __future__ import annotations

from collections import Counter, defaultdict

import networkx as nx
import pandas as pd

from backend.intelligence.fingerprinting import UNKNOWN


def incident_edges(records: pd.DataFrame) -> list[dict]:
    edges: list[dict] = []
    df = records.copy()
    df["_t"] = pd.to_datetime(df["open_time"])
    for key, rel in (("ci_name", "same_ci"), ("kb_number", "same_kb_article"), ("related_change", "same_change")):
        sub = df[df[key].notna() & ~df[key].astype(str).isin(["None", "nan", "Not Available", "Unknown"])]
        if key == "ci_name":
            sub = sub[sub["source"] == "B_event_log"]  # Source A media assets are unique per row
        for val, g in sub.groupby(key):
            if len(g) < 2:
                continue
            g = g.sort_values("_t")
            ids, ts = g["incident_id"].tolist(), g["_t"].tolist()
            for i in range(len(ids) - 1):  # chain edges keep the graph linear in group size
                edges.append({"src_id": ids[i], "dst_id": ids[i + 1], "rel_type": rel, "weight": 1.0,
                              "tag": "observed", "evidence": {key: str(val)}})
                if rel == "same_ci" and pd.notna(ts[i]) and pd.notna(ts[i + 1]):
                    gap = (ts[i + 1] - ts[i]).total_seconds() / 86400
                    if gap <= 7:
                        edges.append({"src_id": ids[i], "dst_id": ids[i + 1], "rel_type": "repeat_same_ci",
                                      "weight": round(1 - gap / 7, 3), "tag": "observed",
                                      "evidence": {"ci_name": str(val), "gap_days": round(gap, 2)}})
    if "near_dup_group" in df:
        for g, grp in df.groupby("near_dup_group"):
            ids = grp["incident_id"].tolist()
            for i in range(len(ids) - 1):
                edges.append({"src_id": ids[i], "dst_id": ids[i + 1], "rel_type": "near_duplicate", "weight": 1.0,
                              "tag": "derived", "evidence": {"near_dup_group": str(g)}})
    return edges


def family_graph(families: dict, records: pd.DataFrame, assign: dict[str, str]) -> dict:
    """Nodes/edges for visualising families, their root causes and components."""
    g = nx.Graph()
    rc_to_fams = defaultdict(list)
    for fid, fam in families.items():
        g.add_node(fid, kind="family", label=fam.name, size=len(fam.members), status=fam.status)
        for fld, kind in (("root_cause", "root_cause"), ("component", "component")):
            for val, share in fam.signature.get(fld, {}).items():
                if val == UNKNOWN or share < 0.2:
                    continue
                node = f"{kind}:{val}"
                g.add_node(node, kind=kind, label=val)
                g.add_edge(fid, node, weight=share, tag="derived", rel=f"has_{kind}")
                if fld == "root_cause" and share >= 0.4:
                    rc_to_fams[val].append(fid)
    # families sharing CIs (observed)
    df = records[records["source"] == "B_event_log"][["incident_id", "ci_name"]].copy()
    df["family"] = df["incident_id"].map(assign)
    ci_fams = df.dropna().groupby("ci_name")["family"].apply(lambda s: sorted(set(s)))
    shared = Counter()
    for fams in ci_fams:
        for i in range(len(fams)):
            for j in range(i + 1, len(fams)):
                shared[(fams[i], fams[j])] += 1
    for (a, b), n in shared.items():
        if n >= 5:
            g.add_edge(a, b, weight=n, tag="observed", rel="shared_cis")
    for rc, fams in rc_to_fams.items():
        for i in range(len(fams)):
            for j in range(i + 1, len(fams)):
                g.add_edge(fams[i], fams[j], weight=1.0, tag="derived", rel="shared_root_cause", root_cause=rc)
    data = nx.node_link_data(g)
    data["links"] = data.pop("links", data.pop("edges", []))
    return data


def incident_neighbourhood(edges_df: pd.DataFrame, incident_id: str, limit: int = 30) -> list[dict]:
    sub = edges_df[(edges_df["src_id"] == incident_id) | (edges_df["dst_id"] == incident_id)]
    return sub.head(limit).to_dict(orient="records")
