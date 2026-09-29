# Latency & cost

_Generated from `data/evaluation/evaluation_results.json` (run `EVAL-ae1233c3`). Device: **cuda:NVIDIA GeForce RTX 4070 Ti**._

## Per-stage latency of the analysis pipeline (ms)

| stage | n | median | p95 | mean |
|---|---|---|---|---|
| query_processing | 129 | 0.340 | 0.516 | 0.350 |
| embedding | 129 | 7.190 | 11.352 | 7.870 |
| vector_search | 129 | 13.790 | 14.774 | 13.945 |
| bm25 | 129 | 7.700 | 12.048 | 7.959 |
| hybrid_fusion | 129 | 0.060 | 0.070 | 0.066 |
| reranking | 129 | 19.640 | 24.732 | 19.571 |
| fingerprint | 129 | 0.510 | 0.806 | 0.530 |
| pattern_match | 129 | 7.500 | 11.496 | 8.414 |
| novelty | 129 | 0.040 | 0.040 | 0.051 |
| resolution_ranking | 129 | 1.177 | 1.579 | 1.196 |
| evidence_chain_assembly | 129 | 0.160 | 0.189 | 0.163 |
| end_to_end_analysis_pipeline | 129 | 59.608 | 70.375 | 60.116 |
| hybrid_retrieval_only | 257 | 53.390 | 62.116 | 53.488 |
| llm_generation | 40 | 13135.379 | 20705.287 | 14494.563 |
| llm_validation | 40 | 1470.387 | 8444.126 | 2615.577 |


## LLM stages

Measured with a local `local:Qwen/Qwen2.5-3B-Instruct` on the same GPU, live calls only (80 calls, 0 cache hits): generation median 13.1 s, p95 20.7 s (n=40); validation median 1.5 s, p95 8.4 s (n=40).

## Trade-offs made

* **One incident = one chunk.** ~3k chunks keep BM25 and vector search well under 20 ms each; no chunk fan-out or result de-fragmentation is needed.
* **Cross-encoder on the top 30 fused candidates only.** Reranking is the most expensive retrieval stage; 30 candidates keep it at tens of ms on a GPU (a few hundred ms on CPU) while the evaluation shows the fused list already contains the relevant incidents (see Hit@5 of `hybrid_rrf`).
* **Deterministic first, LLM last.** Query translation, fingerprinting, family matching, novelty, ranking, confidence and the Evidence Chain use no LLM calls. An LLM is used only for (optional) query expansion when the rules find < 2 concepts, resolution synthesis and validation — at most 3 calls per request.
* **Caching.** LLM responses are cached on disk (`data/processed/llm_cache.jsonl`); models are loaded once per process; KB additions only rebuild BM25 (sub-second) and upsert one vector.
* **Duplicate collapsing before ranking.** Retrieval runs over canonical records only, so 22 identical tickets cost one candidate slot instead of 22.
* **Cost.** In retrieval-only mode the marginal cost per request is local compute only. With an API LLM (e.g. gpt-4o-mini) a full analyze call uses ~1–3 LLM calls of a few hundred tokens each.