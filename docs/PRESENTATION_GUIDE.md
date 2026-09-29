# Presentation guide: how the Incident Assistant works

A speaking guide for presenting the system: what it does, how each stage works, why each choice was made, how it runs with no API key, and how it was evaluated. Every number below comes from the repo (`docs/EVALUATION.md`, `docs/LATENCY.md`, `data/evaluation/*.json`, `backend/`), run `EVAL-ae1233c3`, 2026-09-28.

---

## 1. The one-minute pitch

> An engineer types an incident in plain words. The system finds the most similar past incidents, works out which known **pattern family** it belongs to, and recommends **one** evidence-backed first step, with a confidence score that is computed, not guessed. If nothing in history is similar enough, it says so and routes to a fresh investigation instead of forcing a wrong fix.

Three ideas to repeat during the talk:

1. **Retrieval, not generation.** Fixes are copied from real historical resolution notes. The system does not invent them.
2. **Every number is derived.** Confidence, novelty and grades come from calibrated models and formulas, not from an LLM.
3. **It works with no API key.** The LLM is optional. Without it the app runs in a labelled "Retrieval-only mode".

---

## 2. The data (say this up front, it is the honest framing)

| Source | What it is | Used for |
|---|---|---|
| Source A | `incidents_structured.xlsx`, 150 tickets with real free text (description, solution) | Retrieval text |
| Source B | `incidents_text.csv`, 46,606 real ITSM records with structured fields and timestamps only, **no free text** | Outcomes, timing, reopen rates, relationships |

- The two files share **no IDs** (0 overlap), so they are processed as two pipelines feeding one schema.
- Source B has no text, so text was **generated** by a local LLM (Qwen2.5-3B-Instruct), conditioned on each record's real fields (CI name, impact, urgency, closure code, reassignments). It only chooses wording; the facts come from the record.
- The knowledge base has **3,129 incidents**: 150 original text, 2,979 with generated text (~95% of text cells are synthetic).
- Every field carries a **provenance tag** (original / synthetic / inferred / derived), so nothing generated is passed off as real.

**Caveat to state yourself:** absolute scores describe this corpus. They are not a promise for arbitrary real tickets. Saying it first builds trust.

---

## 3. Chunking

**Strategy: one incident = one chunk** (`backend/data_pipeline/chunking.py`).

Each chunk is:

```
Category: Storage | Severity: high | Impact scope: ...
<Title>. <Description>
Resolution: <Resolution notes>
```

- A short **metadata header** (category, CI type, severity, impact scope) is embedded together with the text, so the vector carries context, not only words.
- The resolution is kept **in the same chunk** as the symptom. Search matches on symptoms, and the answer arrives with it.
- A description is split only if it exceeds **300 words**, and then **on sentence boundaries** into pieces of at most 200 words. No fixed windows.
- In practice no split happened: **3,129 incidents → 3,129 chunks**, mean ~59 words (max 109).

**Why not fixed-size windows?** An incident is the natural unit an engineer would search for. A fixed window would cut symptoms away from their resolution and return fragments. Tickets are short, so chunking finer would only hurt.

---

## 4. The retrieval pipeline, stage by stage

```
Query
  → 1 Query understanding   (rules: vague words → technical terms)
  → 2a Semantic search      (MiniLM embeddings in ChromaDB)   ┐
  → 2b Keyword search       (BM25)                            ┘ run in parallel
  → 3 Reciprocal Rank Fusion (merge the two ranked lists)
  → 4 Cross-encoder rerank  (re-score the top 30)
  → 5 Calibration           (logit → probability)
  → Top 10 incidents, with a "why retrieved" explanation
```

### Stage 1: Query understanding (`query_understanding.py`)
Engineers write "the system feels slow and basic things take forever". Deterministic rules from a lexicon map that to concepts such as *performance degradation, latency, timeout, resource exhaustion*, and add them to the query. They also extract hints (environment, scope, trigger, component). A combination rule adds *memory leak* when "slow" or "hangs" appears together with "a restart fixes it".
It also computes a **specificity score** and an `is_vague` flag, used later to decide whether to ask a clarifying question. An LLM expansion is added only if an LLM is available and the rules found little.

### Stage 2a: Semantic retrieval
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (local, 384-dim, normalised).
- **Vector store:** ChromaDB, embedded, cosine distance.
- Finds incidents that mean the same thing in different words ("can't sign in" ≈ "authentication failure").

### Stage 2b: Keyword retrieval
- **BM25** (`rank_bm25`) over the same chunks, with stop-word removal and a small suffix stemmer.
- Catches exact terms that embeddings blur: error codes, product names, "memory leak".

### Stage 3: Fusion, Reciprocal Rank Fusion (k = 60)
`score(chunk) = Σ 1 / (60 + rank)` across the two lists.
Cosine similarity and BM25 scores are on incomparable scales, so RRF merges **ranks**, not scores. It needs no normalisation and still works if one retriever is missing (the fallback case). Exact duplicates are collapsed **before** ranking so 20 copies of one ticket cannot crowd out distinct evidence.

### Stage 4: Cross-encoder reranking
- **Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (local).
- Takes the top **30** fused candidates and reads the query and each candidate **together**, giving a much sharper relevance score than comparing two separate vectors. It is too slow to run on everything, which is why it runs after the cheap retrievers.

### Stage 5: Calibration
The raw reranker logit is turned into a real probability with **Platt scaling** (`a=0.404, b=0.682`), fitted on 1,280 (query, result) pairs from the **validation** split. So "0.80 relevance" is meant to mean roughly "80% of results like this are truly relevant".

### From results to one recommendation (`rag/resolution.py`)
1. Group retrieved incidents by their **fix strategy**.
2. Each group's evidence mass = Σ relevance × influence, where influence = knowledge-quality score × provenance factor (original 1.0, synthetic 0.8).
3. **Confidence = best relevance × evidence agreement × provenance factor.**
4. **Guardrails:** destructive actions (delete, wipe, reimage, restore, kill session…) need at least 2 independent historical sources and always require human confirmation. Otherwise they are blocked and the next safe strategy is offered.

### Other components (mention briefly if asked)
| Component | Method |
|---|---|
| Fingerprint | Rule/lexicon extraction: component, symptom, failure type, trigger, root cause, environment, scope |
| Pattern families | Agglomerative clustering on description + resolution embeddings + fingerprint fields (30 clusters) |
| Novelty detection | Logistic regression on 4 signals, threshold chosen on validation data |
| Triage models | scikit-learn (TF-IDF + logistic regression; gradient boosting for resolution time and reopen risk) |
| Troubleshooting loop | Failed step excluded → next-best strategy; max 3 rounds; one clarifying question; then escalation L1→L2→L3 |

---

## 5. The LLM: what is used, where, and what happens without an API key

### Short answer
**No API key was used, and the app does not need one.** The key is optional (`LLM_API_KEY` is blank in `.env`). The client detects this on startup and switches to **"Retrieval-only mode — LLM unavailable"** (`backend/rag/llm.py`). The app never crashes because of the LLM.

### What runs locally with no key and no internet
| Part | Model | Where it runs |
|---|---|---|
| Embeddings | all-MiniLM-L6-v2 | Local, in-process |
| Reranker | ms-marco-MiniLM-L-6-v2 | Local, in-process |
| Keyword search | BM25 | Local |
| Vector DB | ChromaDB embedded | Local disk |
| Classifiers, novelty, clustering | scikit-learn | Local |
| **Recommended fix text** | **Copied verbatim from a historical note** | Local |

This is the key point: the core product is **retrieval, statistics and small local models**. An LLM is not in the critical path.

### Where an LLM is used, and what happens without one
| Use | With an LLM | Without a key (current setup) |
|---|---|---|
| **Building the dataset** | Local Qwen2.5-3B-Instruct wrote the ticket text for Source B, one time, offline. Outputs are cached in `synthetic_text_cache.jsonl`, so a rebuild reproduces the same data without a GPU or key. | Uses the cache. Nothing needed at runtime. |
| Query expansion | Adds technical terms when the rules find fewer than 2 | Skipped. Rule-based expansion only. |
| Resolution synthesis | Rewrites the top historical notes as 2–4 steps, citing incident IDs | Skipped. The exact historical step is shown. |
| Synthesis validation | 2nd call judges each step SUPPORTED / UNSUPPORTED | Skipped. |
| Confidence, novelty, family match, grades | **Never an LLM**, always computed | Same |

### How the LLM client is wired (if asked how it "works")
- Three providers: `openai` (any OpenAI-compatible `/chat/completions` endpoint: OpenAI, NVIDIA NIM, Ollama, LM Studio), `local` (a Hugging Face model in-process, no key needed), `none`.
- If the key is empty, the provider is unknown, or a call fails, `complete()` returns `None` and callers take the fallback path. The UI shows an orange banner: *"Retrieval-only mode — LLM unavailable. Every result comes from historical evidence and computed scores; no text was generated."*
- Responses are cached on disk (hash of provider, model, prompt) to avoid repeat calls.
- Temperature is 0.1 and the prompt says "use ONLY these notes; never invent commands".

### Why this design
1. **Trustworthy.** Faithfulness in retrieval-only mode is 0.992, because the answer is a real note, not a paraphrase.
2. **No cost, no data leaving the machine.** Incident data can be sensitive. No third-party API sees it.
3. **Robust.** No outage, quota or key problem can take the tool down.
4. **Honest about LLM risk.** When we *did* test a small local LLM (see §6), the generated steps were far less faithful than the copied ones, which validates keeping it optional.

---

## 6. Evaluation

### How the evaluation is built (so the numbers can be trusted)
- **Query set:** 297 queries. Validation: 128 known + 19 novel. Test: 129 known + 21 novel.
- **Known queries** are LLM rewrites in three styles (**lay, vague, technical**) of held-out KB incidents, with CI names, service names and root-cause wording **removed**, so the system cannot match on leaked words.
- **Novel probes:** 40 seeded off-topic incidents.
- **Leave-one-out:** the source incident is excluded from retrieval.
- **Ground truth** comes from the generator's scenario/strategy labels, never from the system under test. Relevance is graded: **2** = same scenario **and** strategy, **1** = same scenario.
- **Train / validate / test discipline:** thresholds and calibration are fitted on **validation** only. Numbers are reported on **test**. Nothing is hand-picked. If `calibration.json` is missing, the system says "undetermined" instead of inventing a value.
- Uncertainty: 1,000-sample bootstrap 95% confidence intervals.

### 6.1 Retrieval: do the pieces earn their place? (ablation)

| Configuration | MRR | P@1 | P@5 | Hit@5 | nDCG@10 |
|---|---|---|---|---|---|
| BM25 only | 0.864 | 0.833 | 0.827 | 0.907 | 0.521 |
| Semantic only | 0.882 | 0.868 | 0.814 | 0.903 | 0.500 |
| Hybrid (RRF) | 0.891 | 0.872 | 0.842 | 0.918 | 0.526 |
| **Hybrid + rerank (deployed)** | **0.911** | **0.895** | **0.867** | **0.934** | **0.533** |

- Each layer improves on the last, which justifies the extra complexity.
- Deployed config 95% CI: MRR 0.879–0.942, P@5 0.832–0.902, Hit@5 0.907–0.961.
- By query style: lay 0.962 MRR, technical 0.953, **vague 0.817**. Vague queries are the weak spot, and that is why the system asks a clarifying question.
- **Say honestly:** removing query translation did not lower MRR (0.914 vs 0.911), though it slightly improved nDCG@10 (0.533 vs 0.524) and P@5 (0.867 vs 0.859). Recall@K is small by construction (each scenario has 40–220 relevant incidents), so quote P@K, Hit@K, MRR and nDCG instead.

### 6.2 RAG quality (retrieval-only mode, 129 test queries)

| Metric | Value |
|---|---|
| Context precision@5 (RAGAS formula) | 0.921 |
| Context recall | 0.876 |
| Faithfulness | 0.992 |
| Family accuracy@1 | 0.891 |
| **Resolution-strategy accuracy@1** | **0.395** |

- **Read the last row candidly.** Finding the right *family* is strong (89%), but picking the exact *fix strategy* first time is 40%. That is why the product is a **loop**: a failed step is recorded, excluded, and the next-best strategy is proposed.
- **Is confidence meaningful?** Strategy accuracy rises with displayed confidence: 0.11 (≤0.25) → 0.38 → 0.55 → 0.50 (top bucket, only 14 queries). Low confidence really does mean less reliable, though the top two buckets are not cleanly separated.

### 6.3 Optional LLM mode (Qwen2.5-3B, 40 queries)
Faithfulness (NLI judge) **0.279**, all steps grounded 72.5%, 0.375 unsupported steps per answer, and ~13 s generation latency. A small local LLM paraphrases worse than a copy. This is the evidence behind "retrieval-only is the default recommendation". A larger hosted model would need re-evaluation.

### 6.4 Novel-incident detection (test split)

| | Precision | Recall | F1 | False-novel rate |
|---|---|---|---|---|
| Deployed (4-signal logistic model) | 0.955 | 1.000 | 0.977 | 0.008 |
| Baseline (max reranker logit only) | 0.895 | 0.809 | 0.850 | 0.015 |

- Threshold P(known) = 0.4896, chosen as *max novel recall subject to ≤ 2% false-novel on validation*.
- Caveat: only ~20 novel probes per split, so a single error moves recall by ~5 points. Treat as indicative.

### 6.5 Other checks (one line each)

| Area | Result |
|---|---|
| Pattern families | 30 clusters, purity 0.910, NMI 0.906, pairwise F1 0.854. The enriched fingerprint beats text-only clustering (F1 0.380). |
| Category classifier | Accuracy 0.963 (majority baseline 0.839) |
| Priority / impact / urgency classifiers | 0.54–0.57 accuracy, **below the majority baseline** (0.60–0.62). Reported as-is, not relied on. |
| Reopen-risk model | ROC-AUC 0.826, top-decile lift 4.5× |
| Resolution time | Beats baselines but explains little variance (R² 0.046 in log hours). Shown as a median with a P25–P75 range, not a promise. |
| Troubleshooting simulation (129 sessions) | 76% resolved, 1.63 steps on average, 23% escalated |
| Live correlation | Burst recall 1.00, precision 0.78 |
| Evidence-chain completeness | 99.2% of known queries have family + root cause + resolution |
| Knowledge quality manager | Low-quality notes: 100% precision and recall. Seeded contradictions: precision 0.16, recall 0.59, the weakest check, reported as such. |

### 6.6 Per-query grade shown in the UI (`query_eval.py`)
Each analysis gets a Good / Fair / Poor grade: the unweighted mean of retrieval relevance, P(known), family match strength and fix confidence. Cut-offs are 0.70 and 0.40. These are **display bands, not fitted thresholds**, and a novel verdict is always Poor.

### 6.7 Speed (`docs/LATENCY.md`)
End-to-end analysis: **median ~60 ms, p95 ~70 ms** (embedding 7 ms, vector search 14 ms, BM25 8 ms, rerank 20 ms), measured on an RTX 4070 Ti. LLM generation adds ~13 s, which is a further reason the LLM is optional.

---

## 7. Why each choice was made (cheat sheet)

| Choice | Reason |
|---|---|
| One incident per chunk | It is the natural unit; keeps symptom and fix together |
| Metadata header in the chunk | Puts category, severity and scope into the embedding |
| Hybrid retrieval | Embeddings catch meaning, BM25 catches exact terms; measured gain over either alone |
| RRF, not score averaging | Scores are on different scales; ranks are comparable |
| Cross-encoder rerank | Reads query and document together, so it is more accurate; run only on the top 30 for speed |
| Platt calibration | Turns raw logits into probabilities that confidence can be built on |
| Small local models | No key, no cost, data stays on-prem, ~60 ms |
| Extractive fixes | No hallucinated commands; faithfulness ≈ 1 |
| Novelty detector | Better to say "I don't know" than force a wrong fix |
| Guardrails | Destructive actions need ≥ 2 sources and human confirmation |
| Provenance tags | Real vs generated data is never mixed silently |
| Thresholds fitted on validation | Nothing hand-tuned to the test set |

---

## 8. Suggested talk flow (about 10 minutes)

1. **Problem (1 min).** Engineers re-solve the same incidents. Vague reports are hard to search.
2. **Data (1 min).** Two sources, generated text, provenance, and the caveat.
3. **Live demo (2 min).** Analyze the "Memory leak" preset: verdict, single recommended step, confidence breakdown. Then the "Tape robot" preset to show the novel route.
4. **Pipeline (3 min).** Use the diagram in §4: chunking, hybrid, RRF, rerank, calibrate, group into strategies.
5. **No API key (1 min).** The §5 table. Show the "Retrieval-only mode" banner in the app.
6. **Evaluation (2 min).** The ablation table, the strategy-accuracy weakness and why the loop exists, the novelty result.

## 9. Questions to expect

- **"Why no LLM?"** It is optional by design. The recommendation is an exact historical note, so it cannot hallucinate. A small local LLM scored 0.28 faithfulness, worse than copying.
- **"Isn't 95% synthetic text a problem?"** Yes, and we say so. It is labelled per field, downweighted (0.8), and absolute scores describe this corpus. Real outcomes (reopen rate, timing) come from real timestamps.
- **"40% strategy accuracy is low."** First-shot exact-strategy accuracy is 40%. Family accuracy is 89%, and the loop reaches 76% resolution in 1.6 steps on average in simulation.
- **"Why not embeddings only?"** Measured: hybrid + rerank beat semantic-only on every metric (MRR 0.911 vs 0.882).
- **"Can I plug in GPT or another hosted model?"** Yes. Set `LLM_API_KEY`, `LLM_MODEL` and optionally `LLM_BASE_URL` in `.env` and restart. It works with any OpenAI-compatible endpoint, or set `LLM_PROVIDER=local` for an in-process model. Re-run the evaluation first, because faithfulness must be re-measured.
- **"What if the vector DB or reranker is down?"** Documented fallbacks (`docs/FALLBACKS.md`): BM25-only labelled "keyword-only", or fusion order labelled "unreranked" with confidence withheld rather than invented.
