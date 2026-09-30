"""ChromaDB wrapper (if unreachable, callers fall back to BM25-only)."""
from __future__ import annotations

import logging

import numpy as np

from backend.config.settings import Settings, get_settings

log = logging.getLogger(__name__)


class VectorStoreUnavailable(RuntimeError):
    pass


class ChromaStore:
    def __init__(self, settings: Settings | None = None, collection: str | None = None):
        self.s = settings or get_settings()
        self.collection_name = collection or self.s.chroma_collection
        self._client = None
        self._col = None

    # -------------------------------------------------------------- connection
    def _connect(self):
        if self._col is not None:
            return self._col
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            cs = ChromaSettings(anonymized_telemetry=False)
            if self.s.chroma_mode == "http":
                self._client = chromadb.HttpClient(host=self.s.chroma_host, port=self.s.chroma_port, settings=cs)
            else:
                self._client = chromadb.PersistentClient(path=self.s.chroma_path, settings=cs)
            self._col = self._client.get_or_create_collection(
                self.collection_name, metadata={"hnsw:space": "cosine"})
            return self._col
        except Exception as exc:  # noqa: BLE001
            self._col = None
            raise VectorStoreUnavailable(f"ChromaDB unreachable ({type(exc).__name__}: {exc})") from exc

    def healthy(self) -> tuple[bool, str]:
        try:
            col = self._connect()
            return True, f"{self.s.chroma_mode} ok ({col.count()} vectors)"
        except VectorStoreUnavailable as exc:
            return False, str(exc)

    # -------------------------------------------------------------- write
    def reset(self) -> None:
        self._connect()
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001
            pass
        self._col = None
        self._connect()

    def upsert(self, ids: list[str], embeddings: np.ndarray, documents: list[str],
               metadatas: list[dict], embedder_name: str) -> None:
        col = self._connect()
        for i in range(0, len(ids), 1000):
            col.upsert(ids=ids[i:i + 1000], embeddings=embeddings[i:i + 1000].tolist(),
                       documents=documents[i:i + 1000], metadatas=metadatas[i:i + 1000])
        col.modify(metadata={"embedder": embedder_name})

    def embedder_name(self) -> str | None:
        md = self._connect().metadata or {}
        return md.get("embedder")

    def count(self) -> int:
        return self._connect().count()

    # -------------------------------------------------------------- read
    def query(self, embedding: np.ndarray, n: int, where: dict | None = None) -> list[tuple[str, float, dict]]:
        """Return [(chunk_id, cosine_similarity, metadata)] best first."""
        col = self._connect()
        try:
            res = col.query(query_embeddings=[embedding.tolist()], n_results=n, where=where or None,
                            include=["distances", "metadatas"])
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreUnavailable(f"ChromaDB query failed ({exc})") from exc
        ids = res["ids"][0]
        return [(cid, 1.0 - float(d), md) for cid, d, md in zip(ids, res["distances"][0], res["metadatas"][0])]

    def get_embeddings(self, ids: list[str]) -> dict[str, np.ndarray]:
        col = self._connect()
        res = col.get(ids=ids, include=["embeddings"])
        return {i: np.asarray(e, dtype=np.float32) for i, e in zip(res["ids"], res["embeddings"])}
