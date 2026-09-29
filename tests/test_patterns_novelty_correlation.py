"""Pattern clustering, novelty model/threshold rule, live correlation (no models needed)."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from backend.config.settings import Settings
from backend.evaluation.calibration import choose_threshold, novelty_metrics
from backend.intelligence.correlation import LiveCorrelator
from backend.intelligence.fingerprinting import Fingerprinter
from backend.intelligence.novelty import FEATURES, NoveltyDetector, NoveltyModel
from backend.intelligence.pattern_detection import (
    build_families, choose_clusters, cross_symptom_finding, feature_matrix,
)


def _blobs(seed=0):
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(3, 32))
    X = np.vstack([c + 0.08 * rng.normal(size=(30, 32)) for c in centers]).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    return X, [i // 30 for i in range(90)]


def test_clustering_recovers_well_separated_families():
    X, truth = _blobs()
    fpr = Fingerprinter()
    texts = ["the database queries are slow", "users cannot log in to the portal", "the printer does not print"]
    fps = [fpr.from_query(texts[t]) for t in truth]
    F = feature_matrix(X, X, fps, np.ones(len(X), dtype=np.float32))
    labels, k, sweep = choose_clusters(F, k_range=range(2, 7))
    assert k == 3 and len(sweep) == 5
    ids = [f"I{i}" for i in range(90)]
    recs = pd.DataFrame({"incident_id": ids, "description_source": ["synthetic"] * 90})
    fams, assign = build_families(ids, recs, X, F, labels, fps)
    assert len(fams) == 3 and len(assign) == 90
    for fam in fams:  # every family is pure
        assert len({truth[int(m[1:])] for m in fam.members}) == 1
        assert fam.name and fam.signature["symptom"]


def test_cross_symptom_root_cause_discovery():
    fpr = Fingerprinter()
    fps = []
    for text in ["the app is very slow"] * 5 + ["the app freezes and hangs"] * 5:
        fp = fpr.from_query(text)
        fp.values["root_cause"] = "memory leak / heap exhaustion"
        fps.append(fp)
    f = cross_symptom_finding(fps)
    assert f and f["root_cause"] == "memory leak / heap exhaustion" and len(f["symptoms"]) == 2


def test_novelty_model_and_uncalibrated_detector():
    m = NoveltyModel([2.0, 0.0, 1.0, 0.0], 0.0, [0, 0, 0, 0], [1, 1, 1, 1], threshold=0.5)
    known = dict(zip(FEATURES, [5.0, 0.8, 0.7, 0.9]))
    novel = dict(zip(FEATURES, [-10.0, 0.2, 0.2, 0.5]))
    assert m.p_known(known) > 0.99 and m.p_known(novel) < 0.01
    det = NoveltyDetector(Settings(), model=None)
    det.model = None
    retrieval = SimpleNamespace(results=[], mode=SimpleNamespace(reranked=True, semantic_available=True, labels=[]))
    out = det.assess(retrieval, [], None)
    assert out["verdict"] == "undetermined" and out["is_novel"] is None  # never a hand-picked threshold


def test_novelty_detector_refuses_degraded_retrieval():
    det = NoveltyDetector(Settings(), model=NoveltyModel([1, 0, 0, 0], 0, [0] * 4, [1] * 4, 0.5))
    retrieval = SimpleNamespace(results=[], mode=SimpleNamespace(reranked=False, semantic_available=True,
                                                                 labels=["unreranked"]))
    assert det.assess(retrieval, [], None)["verdict"] == "undetermined"


def test_threshold_rule_caps_false_novel_rate():
    rng = np.random.default_rng(0)
    p_known = np.concatenate([rng.uniform(0.6, 1.0, 100), rng.uniform(0.0, 0.3, 20)])
    y_novel = np.array([False] * 100 + [True] * 20)
    thr, m = choose_threshold(p_known, y_novel, max_false_novel=0.02)
    assert m["false_novel_rate"] <= 0.02
    assert m["recall"] == 1.0  # separable data → all novel caught
    assert novelty_metrics(y_novel, p_known < thr)["precision"] == m["precision"]


def _fake(texts_to_family):
    rng = np.random.default_rng(1)
    base = {f: rng.normal(size=16) for f in set(texts_to_family.values())}
    embs = {}
    for t, f in texts_to_family.items():
        v = base[f] + 0.9 * rng.normal(size=16)  # same family, different wording → moderate cosine
        embs[t] = v / np.linalg.norm(v)
    fpr = Fingerprinter()
    analyzer = lambda t: SimpleNamespace(fingerprint=fpr.from_query(t), novelty={"is_novel": False},
                                         families=[{"family_id": texts_to_family[t], "match_strength": 0.8}])
    embedder = SimpleNamespace(embed=lambda ts: np.vstack([embs[t] for t in ts]))
    return embedder, analyzer


def test_correlation_flags_burst_and_ignores_unrelated_and_expired():
    t = {"db slow 1": "F1", "db slow 2": "F1", "printer jam": "F2", "vpn drops": "F3", "db slow 3": "F1"}
    emb, analyzer = _fake(t)
    s = Settings(correlation_window_minutes=30, correlation_min_incidents=2)
    c = LiveCorrelator(s, None, Fingerprinter(), emb, persist=False, similarity_threshold=0.99, analyzer=analyzer)
    t0 = datetime(2026, 1, 1, 9)
    assert c.ingest("db slow 1", t0, "A")["alert"] is None
    assert c.ingest("printer jam", t0 + timedelta(minutes=2), "B")["alert"] is None
    r = c.ingest("db slow 2", t0 + timedelta(minutes=5), "C")
    assert r["alert"] and set(r["alert"]["members"]) == {"A", "C"}
    assert r["alert"]["detection_latency_s"] == 300
    assert c.ingest("vpn drops", t0 + timedelta(minutes=6), "D")["alert"] is None
    late = c.ingest("db slow 3", t0 + timedelta(minutes=80), "E")  # outside the 30-min window
    assert late["alert"] is None
