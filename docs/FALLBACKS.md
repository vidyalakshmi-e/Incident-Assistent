# Fallback & error handling (single source of truth)

The system degrades gracefully and never returns a degraded answer that looks like a full-confidence
one. Every fallback below is implemented explicitly, labelled in the API response
(`mode_labels` / `retrieval.mode.labels`) and in the UI (orange banner), and covered by a test.

| # | Situation | Behaviour | User-visible label | Code | Test |
|---|---|---|---|---|---|
| 1 | `LLM_API_KEY` missing, provider unreachable, or an LLM call fails | App starts normally. Retrieval-only mode: ranked hybrid results, fingerprint, family, novelty verdict, Evidence Chain, extractive top resolution. **No** LLM synthesis, **no** LLM validation, no LLM query expansion. | `Retrieval-only mode — LLM unavailable` | `backend/rag/llm.py` (`LLMClient.available`, `complete()` returns `None`), `backend/evidence/chain.py` (`llm_inference.label`) | `test_llm_missing_gives_labelled_retrieval_only_mode` |
| 2 | Embedding provider unavailable / misconfigured (`EMBEDDING_PROVIDER=openai\|nvidia` without a working key) | Falls back to local `sentence-transformers/all-MiniLM-L6-v2`; the provider actually used is logged and reported by `/health` (`embeddings.provider`, `fallback_reason`). If the index was built with a different embedder, semantic search is disabled rather than mixing vector spaces (→ #6). | `/health` + retrieval `mode.notes` | `backend/retrieval/embeddings.py` (`EmbeddingService`), `HybridRetriever._check_vector_embedder` | `test_embedding_provider_misconfigured_falls_back_to_local` |
| 3 | Reranker unavailable / misconfigured | Configured → local `cross-encoder/ms-marco-MiniLM-L-6-v2` → none. With no reranker, results keep hybrid-fusion order, **no confidence is shown** (it would be invented), and novelty is "undetermined". | `unreranked` | `backend/retrieval/reranker.py` (`RerankerService`), `backend/retrieval/hybrid.py` | `test_reranker_unavailable_results_are_labelled_unreranked` |
| 4 | No sufficiently strong historical match | Novel Incident Detector returns `NOVEL INCIDENT — no sufficiently similar historical incident found`; no low-confidence top-1 fix is forced; the Evidence Chain marks family / root cause / resolution as "insufficient evidence"; routed to fresh investigation (Escalation Agent). | `NOVEL INCIDENT …` | `backend/intelligence/novelty.py`, `backend/evidence/chain.py`, `Platform.resolve` | `test_novel_probe_is_flagged_and_evidence_is_not_fabricated` |
| 5 | Top-ranked resolution reported as failed | Attempt recorded (`FAILED`, `excluded_from_next_suggestion=True`); the strategy **and near-identical actions** are excluded; secondary retrieval picks the next-best evidence-backed action (matched-family strategies first); after the round cap a clarification check runs, then escalation with full attempt history. | step history in UI | `backend/troubleshooting/session.py` | `test_failed_step_is_excluded_and_loop_escalates_with_history` |
| 6 | ChromaDB unreachable (embedded store broken or HTTP server down) | BM25-only keyword retrieval; the vector store is re-checked every 30 s (e.g. a Chroma server started after the API); novelty is "undetermined" in this mode. | `keyword-only (semantic search unavailable)` | `backend/retrieval/vector_store.py` (`VectorStoreUnavailable`), `backend/retrieval/hybrid.py` | `test_vector_db_unreachable_gives_keyword_only` |
| 7 | Ambiguous / under-specified query | Not an error: **Clarification Before Escalation** asks one targeted question (max one per session) when (1) confidence is low and the query is vague, (2) two families match within a margin and a fingerprint field separates them, or (3) the loop is about to escalate and a missing detail could enable one more targeted step. The escalation packet records what was asked and learned. | question card | `backend/troubleshooting/clarification.py` | `tests/test_troubleshooting_units.py::test_asks_*` |

Additional safety fallbacks (SAFETY / GUARDRAILS):

* **Destructive actions** (delete, drop, truncate, wipe, reimage, restore-from-backup, kill session …)
  are only recommended with ≥ 2 independent historical sources and are always marked
  "requires human confirmation"; otherwise they are listed under `blocked_by_guardrails` and the
  next safe strategy is recommended. `backend/rag/guardrails.py`, `test_destructive_action_needs_two_sources`.
* **Unsupported LLM steps** (no grounding in a cited note, invalid citation, or an LLM validator
  verdict of UNSUPPORTED) are flagged and kept separate from historical evidence. `backend/rag/synthesis.py`.
* **Uncalibrated components** never invent numbers: without `data/evaluation/calibration.json` the
  novelty verdict is "undetermined" and the confidence basis says "not yet calibrated".
