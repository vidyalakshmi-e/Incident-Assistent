"""BM25 keyword index (rank_bm25). Rebuilt in memory from the KB table — it is small enough
(a few thousand incident chunks) that a rebuild after a KB-evolution update takes well under a second."""
from __future__ import annotations

import re

import numpy as np
from rank_bm25 import BM25Okapi

STOPWORDS = set("""a an the and or but if then else of to in on at by for with from as is are was were be been
being it its this that these those i we you they he she my our your their me us them do does did done have has
had not no so very can could would should will just also into after before when while than there here out up
about all any some more most other such only own same too s t""".split())

_WORD = re.compile(r"[a-z0-9]+")


def stem(tok: str) -> str:
    """Tiny, deterministic suffix stripper (keeps the dependency list short)."""
    for suf in ("ations", "ation", "ing", "edly", "ed", "es", "s", "ly"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)]
    return tok


def analyze(text: str) -> list[str]:
    return [stem(t) for t in _WORD.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


class BM25Index:
    def __init__(self, chunk_ids: list[str], texts: list[str]):
        self.chunk_ids = list(chunk_ids)
        self.tokens = [analyze(t) for t in texts]
        self.bm25 = BM25Okapi(self.tokens)
        self._pos = {c: i for i, c in enumerate(self.chunk_ids)}

    def search(self, query: str, n: int, allowed: np.ndarray | None = None) -> list[tuple[str, float, list[str]]]:
        """Return [(chunk_id, score, matched_terms)] for the top-n (score > 0) chunks.

        `allowed` is an optional boolean mask implementing metadata filters."""
        q = analyze(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        if allowed is not None:
            scores = np.where(allowed, scores, 0.0)
        top = np.argsort(-scores)[:n]
        qs = set(q)
        return [(self.chunk_ids[i], float(scores[i]), sorted(qs & set(self.tokens[i])))
                for i in top if scores[i] > 0]

    def matched_terms(self, query: str, chunk_id: str) -> list[str]:
        i = self._pos.get(chunk_id)
        return [] if i is None else sorted(set(analyze(query)) & set(self.tokens[i]))
