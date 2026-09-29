# Design document

> An AI-powered Incident Intelligence and Troubleshooting platform that combines hybrid retrieval with
> historical incident pattern discovery (including causal chain reasoning), novel-incident detection,
> live incident correlation, resolution intelligence, transparent evidence-backed recommendations, and
> a knowledge base that evolves from every resolved incident.

```
Traditional:  Incident → Search → Similar tickets → Answer
This system:  Incident → Understand → Enriched fingerprint → Pattern + causal chain → Known vs. novel
              → Historical resolution strategies → Ranked top fix with full evidence trail
              → Guided, attempt-tracked troubleshooting → Detect related ongoing incidents
              → Escalate with complete context → Postmortem → Feed validated knowledge back in
```

The **four major differentiators** are Pattern Intelligence, Novel Incident Detection, Live Incident
Correlation and Resolution Strategy Intelligence. The Enriched Fingerprint, Causal Chain, Resolution
Attempt Tracking, Evidence Chain and Knowledge Base Evolution are *depth upgrades* of those four —
not separate innovations. Hybrid retrieval, reranking, RAG, classification, escalation, agents,
evaluation and feedback are required core features, not innovations.

Numbers quoted here come from `docs/EVALUATION.md` / `docs/DATASET_REPORT.md` (generated from JSON).

---

## 1. Data: what exists, what was generated, and why

### 1.1 Inspect before assuming
Profiling (`backend/data_pipeline/profiling.py`) found that the attached filenames are **swapped**
relative to their content, so sources are detected by content (`loaders.detect_sources`). Other
findings that shaped the design:

* **No join key.** Source A IDs `INC-5xxx`, Source B IDs `IM00xxxxx`, different domains (media-server
  ops vs. banking ITSM). The sources are two independent pipelines feeding one unified schema — no
  fake join. Source A provides real free text; Source B provides real outcome / time / relationship
  signal (46,606 incidents).
* **Source A has 7 unique texts** repeated 21–22× and a **misaligned Category column** (e.g. "Database
  Timeout" labelled *Hardware*). The original category is kept (`category_original`); a corrected
  category is derived from the text (`category_source = derived`) and the conflict is a real
  Quality-Manager finding.
* **Mixed date formats are all day-first** (`d/m/yyyy` when day ≤ 12, `dd-mm-yyyy` otherwise).
  Durations are recomputed from timestamps; `Handle_Time_hrs` is corrupted (Indian-style digit
  grouping or decimal commas that disagree with the timestamps) and is only classified, never used.
* **Placeholders** (`NS`, `NA`, `#N/B`, `#MULTIVALUE`, Dutch closure codes) become explicit,
  documented values; no row is dropped.
* **No sequential-attempt log, no assignment group / assignee, no environment field.** Therefore:
  troubleshooting uses secondary retrieval (not sequence mining); routing/expertise is derived from
  CI category + fingerprint only (no individual-level claims); `environment` stays Unknown unless text
  states it.

### 1.2 Conditioned synthetic text (Step 4)
Source B has no text, but retrieval needs text. For a **stratified sample of ~3,000 real Source B
incidents** a text was generated, *conditioned on that row's real fields*:

| Real field | How it conditions the text |
|---|---|
| CI_Subcat (→ CI group) | which scenarios are compatible (a SAN incident never gets a VPN story) |
| Closure_Code | scenario eligibility + which resolution strategy is chosen |
| No_of_Reassignments | quick workaround vs. engineering fix; "went through several teams" |
| Impact / Urgency | affected-scope and urgency phrasing |
| Related_Change | raises the prior of change-related scenarios |
| CI_Name | the real configuration item is named in the text |

A deterministic *brief* (scenario, strategy, reporter view, trigger, scope, note quality) is sampled
per row (`synthetic.plan_synthetic_rows`), then an **LLM (local Qwen2.5-3B-Instruct)** writes the
title / description / resolution notes from the brief (`llm_verbalizer.py`). Outputs are cached
(`synthetic_text_cache.jsonl`) so the dataset rebuilds identically without a GPU; without the cache
and without an LLM the same briefs are verbalised by a conditioned template grammar.

Variety seeded on purpose:
* **same root cause, different wording** — user / monitoring / engineer symptom views per scenario
  (Pattern Intelligence must discover the shared root cause);
* **2–3 genuinely different resolution strategies per scenario** (Resolution Strategy Intelligence);
* **40 no-match probes** — evaluation-only, never indexed (Novel Incident Detection validation);
* **low-quality notes** ("closed", "fixed"; more likely for vague closure codes) and **1.5% notes from
  another family** (Knowledge Quality Manager).

Why a sample and not all 46k rows? Text is only required for knowledge-base documents; generating it
for every row would make the KB >99% synthetic and multiply near-duplicates, while all real rows
already feed the outcome models, recurrence and hotspot analyses. No synthetic *rows* were added to
the KB (Step 4B augmentation was not needed); the only synthetic rows are the 40 evaluation probes.

Honest consequence: ~95% of KB text is synthetic. Every such value is tagged `synthetic`, discounted
in ranking (provenance factor 0.8) and shown with an amber chip in the UI.

### 1.3 Field-level provenance
Each tracked field has a companion `<field>_source` ∈ {original, derived, synthetic, missing}.
Taint propagates: a value derived from synthetic text is itself `synthetic`. Provenance is stored in
the parquet artefacts, in SQL (`Incident.provenance`), in Chroma metadata (`text_source`) and is
returned with every retrieved incident.

## 2. Knowledge base construction

### 2.1 Strategic chunking — one incident = one chunk
An incident is the natural retrieval unit: splitting on a fixed window would separate symptoms from
their resolution. Each chunk embeds a metadata header (category, CI type, derived severity, impact
scope) together with title, description and resolution, so structured context participates in
semantic and keyword matching. Only descriptions longer than 300 words would be split, and only on
sentence boundaries (`chunking.py`); none of the current incidents needs it.

### 2.2 Knowledge Quality Manager (built before fingerprinting)
`knowledge/quality.py` flags empty / too-short / generic notes, exact duplicates (text-identical) and
near duplicates (cosine ≥ 0.95), and contradictions: text-vs-category (real, Source A),
closure-code-vs-note, priority-matrix violations (real: Priority ≠ min(Impact, Urgency)), and a note
that resembles none of the ways similar incidents were fixed (entity-masked neighbour comparison,
data-driven 5th-percentile fence). Score = 0.5·detail + 0.15·completeness + 0.2·consistency +
0.15·outcome (reopened / heavy reassignment lowers it). Influence weight = score × provenance factor.

Exact duplicates are **collapsed before ranking** (retrieval runs over canonical records; group size
is reported), so 22 copies of one ticket occupy one slot and count as one piece of evidence.

## 3. Hybrid retrieval

* **Query understanding** (`query_understanding.py`) maps lay phrasing to technical concepts with a
  documented lexicon (e.g. "takes forever" → performance degradation / latency; "restarting fixes it
  temporarily" + slowness/freeze → memory leak / resource exhaustion) and extracts hints
  (environment, scope, trigger, component). LLM expansion is used only if an LLM exists and the rules
  found < 2 concepts (tagged *inferred*).
* **Semantic** (ChromaDB, cosine) + **BM25** (rank_bm25 with a small stemmer) → **Reciprocal Rank
  Fusion** (k = 60). RRF was chosen because cosine and BM25 scores are on incomparable scales and RRF
  degrades gracefully to a single retriever (the ChromaDB fallback).
* **Metadata filters**: priority, impact, urgency, state, category, team (derived), CI group, source,
  text provenance, time period, min quality, excluded IDs — applied in Chroma (`where`) and BM25 (mask).
* **Cross-encoder** (ms-marco-MiniLM-L-6-v2) reranks the top 30; its logits are **Platt-calibrated**
  on the validation split (P(relevant | logit)) — this is the displayed relevance confidence.
* Each result carries a structured **why_retrieved** (retriever ranks, matched terms / concepts,
  cross-encoder relevance, filters) that feeds the Evidence Chain.

## 4. Enriched Incident Fingerprint

Ten fields (component, service, symptom, failure_type, trigger, root_cause, environment, dependency,
business_impact, impact_scope), each with provenance and the evidence phrase / field it came from.
Built once (`intelligence/fingerprinting.py`) and reused by Pattern Intelligence, Novelty, Correlation,
Clarification and the Evidence Chain. Rules: text first, then real structured fields (CI_Subcat →
component, Impact → scope, Closure_Code → coarse root cause / failure type, Related_Change → trigger).
A *new* incident's root cause is normally Unknown — it is inferred from matched history, never
invented. Caveat: the lexicons were written with domain knowledge that overlaps the synthetic scenario
catalogue, so extraction on synthetic text is optimistic.

## 5. Incident Pattern Intelligence Engine (Differentiator 1)

One engine, presented as one feature:
* **Families**: agglomerative clustering (cosine, average linkage) over a combined vector —
  symptom-text embedding + entity-masked resolution embedding + weighted one-hot fingerprint blocks
  (root cause 0.9, component 0.5, symptom 0.4, failure type 0.3). The number of families is chosen by
  **silhouette** (no ground truth involved). Weights were fixed a priori; the ablation in EVALUATION
  shows what the fingerprint adds over text-only clustering.
* **Cross-symptom root-cause discovery**: families where ≥ 2 symptom presentations (each ≥ 10%) share
  one dominant root cause (≥ 60%). The engine also merges the real Source A templates with their Source
  B counterparts (e.g. Source A "Database Timeout" joins the slow-query family).
* **Recurrence** from real timestamps: monthly counts, median inter-arrival, CIs with repeats within
  30 days. **Proactive prevention** runs on all 46,606 real rows (CI hotspots: max incidents in any
  14-day window) and is always phrased "potential pattern requiring investigation".
* **Evolution / failure chains**: family A → B on the same CI within 14 days, reported only with
  support ≥ 5 and lift ≥ 2 over independence (none met the bar on this data — reported as such).
* **Relationship graph**: observed edges (same CI, repeat on same CI within 7 days, same KB article,
  same change) and derived edges (near duplicate, shared dominant root cause).

### 5.1 Causal chain (a formal output of the engine)
`Trigger → Technical Failure → Symptom → Business Impact → Resolution → Outcome`, each link tagged:

| Tag | Rule |
|---|---|
| observed | a real related-change record (the *link* is recorded, causal direction is stated as not recorded); verbatim original text; real Open/Resolved/Reopen timestamps |
| derived | computed from real fields by a documented rule (Closure_Code → failure class, Impact/Urgency → business impact, rules over original text) |
| inferred | extracted from generated (synthetic/LLM) text or produced by an LLM |

No chain is built for an incident without timestamps (all Source A rows): the unordered facts are
returned with the reason. The UI draws observed links solid, derived dashed, inferred dotted. Rule
conformance is checked automatically in the evaluation (100%).

## 6. Novel Incident Detection (Differentiator 2)

Four real signals (best cross-encoder logit, best embedding cosine, best family-centroid similarity,
fingerprint-symptom support) → logistic model → P(known). Weights **and** threshold are fitted on the
validation split of a labelled set (LLM-paraphrased known incidents vs. seeded no-match probes). The
operating point is chosen by a rule, not by hand: *maximise novel recall subject to a false-novel rate
≤ 2% on validation known incidents* — estimated on the large known class, which proved far more stable
than optimising F1 on ~20 novel probes (an F1-optimal threshold flipped between runs). Reported on the
held-out test split, with a single-feature baseline for comparison. Without calibration, or in a
degraded retrieval mode, the verdict is "undetermined".

## 7. Live Incident Correlation (Differentiator 3)

`intelligence/correlation.py`: every incoming ticket is analysed like a query; two tickets inside the
window (30 min) are linked if they map to the same family by retrieval evidence (not novel, match ≥
0.3) or are textually near-identical (validated threshold). Connected components of ≥ 2 tickets raise
"possible single ongoing incident" alerts with detection latency. "Simulate Incoming Incident"
presets (DB outage burst, VPN storm, memory leak, unrelated noise) make the demo independent of real
ticket traffic. The text-similarity threshold is selected on simulated validation streams.

## 8. Resolution intelligence (Differentiator 4) and the output rule

* **Ranked single top pick first** (`rag/resolution.py`). Retrieved incidents with usable notes are
  grouped by historical strategy; evidence mass = Σ relevance × influence weight. After a failure,
  the matched family's untried strategies are preferred (family prior when match strength ≥ 0.5),
  so fallbacks stay within the diagnosed pattern.
* **Confidence** = best calibrated relevance × evidence agreement × provenance factor — every factor
  is a computed number; unreranked results show "undetermined".
* **Strategy panel** (secondary, expandable): all historically observed strategies of the family
  (clustered on the *action clauses* of the notes, entity-masked). Reopen rate (Wilson 95% CI), median
  resolution time and mean reassignments are shown **only** when ≥ 20 members have real outcome data;
  otherwise "historical resolutions observed for this pattern". Labels separate *observed historical
  resolution* / *inferred recommendation* (our ranking) / *LLM-generated synthesis*. Because strategy
  wording is synthetic but conditioned on real Closure_Code / reassignments, the statistics describe
  the real incident populations those strategies were assigned to, not an intrinsic effect of the text.
* **Guardrails**: destructive actions need ≥ 2 independent sources and human confirmation; disruptive
  actions carry a change-window note; LLM steps are grounded / validated.

## 9. Interactive troubleshooting with formal attempt tracking

Formal record per attempt: `attempt_id | incident_id | step_description | expected_observation |
engineer_response (WORKED/FAILED/UNKNOWN) | timestamp | excluded_from_next_suggestion` (+ strategy,
evidence IDs, confidence). FAILED excludes the strategy and any near-identical action (masked
action-clause cosine ≥ 0.5; restart paraphrases measured 0.68–0.73, different actions 0.08–0.12);
UNKNOWN skips it for one pick. Cap = 3 rounds. **Sequence mining is not used**: the data has no
sequential-attempt evidence, so the next step always comes from secondary retrieval.

**Clarification before escalation** (`troubleshooting/clarification.py`): three ordered triggers,
one question per turn, max one per session, never about a known field; the answer updates hints and the
fingerprint and re-runs retrieval; after the round cap an informative answer buys exactly one more
targeted step. The escalation packet records what was asked and learned.

## 10. Agents (LangGraph) — scoped, not role-play

| Agent | Responsibility | Tools (distinct) |
|---|---|---|
| Pattern Intelligence | what is this incident? | read-only retrieval, fingerprinter, family match, causal-chain store, novelty detector |
| Diagnostic | what to try next? | resolution ranker, exclusion retrieval, attempt tracker (write), clarification policy, LLM synthesis/validation |
| Escalation | who takes over, with what context? | triage models, configurable tier router, team/expertise router, escalation records (write) |

Hand-offs are conditional graph edges and typed A2A messages returned by the API. Tier order is a
config value (`ESCALATION_TIERS`, default `L1,L2,L3`) — to be confirmed against the grading rubric.

## 11. Triage models (real data)

* Text classifiers (TF-IDF + LR) for category / priority / impact / urgency when fields are missing
  (optimistic on synthetic text — stated in the report).
* Resolution-time: gradient boosting on log-hours with features known at open time, time-based split,
  plus P25/P75 quantile models (the target is extremely heavy-tailed; the model beats baselines but R²
  is low — reported honestly).
* Fix-accuracy: P(reopen) from real Reopen_Time labels (fields known at resolution time); family- and
  strategy-level first-time-fix rates only with ≥ 20 real outcomes.

## 12. Evidence Chain

A structured object on every recommendation (`evidence/chain.py`): query understood, extracted
fingerprint, matched family (+ runner-up, novelty), retrieved incidents with why-retrieved, root-cause
evidence (supporting incidents, fields, provenance, certainty wording), resolution evidence (evidence
rows, confidence components, outcome stats, safety), evidence strength per dimension (component /
symptom / environment / pattern — computed shares, or "insufficient evidence"), an **LLM-inference
section kept separate from historical evidence**, mode labels and a completeness score. Assembled at
query time (no table), cached per incident for `GET /incidents/{id}/evidence-chain`; for historical
incidents it is recomputed leave-one-out.

## 13. Knowledge Base Evolution

Resolved incident → attempt history + final outcome → feedback → Quality Manager re-score →
≥ 0.55: fingerprint → family (or new *emerging* family) → graph edges → vector upsert → BM25 rebuild;
< 0.55: manual review queue (approve / reject). Runs on demand in the demo (feedback or postmortem) and
as a nightly batch (`scripts/kb_evolution_batch.py --loop`). Every stage is written to `kb_evolution_events`. Negative feedback
lowers the influence of the historical records behind a recommendation. **No model is retrained.**

## 14. Confidence policy

Confidence anywhere is a computed number: calibrated cross-encoder relevance, family match strength
(vote share × best relevance), resolution confidence (relevance × agreement × provenance), novelty
P(known) from a validated model. If the signal is missing (unreranked, uncalibrated, no evidence) the
UI says "undetermined". The LLM is never asked for a confidence score.

## 15. Known limitations

* ~95% of KB text is LLM-generated (conditioned); absolute metrics describe this corpus.
* Rule lexicons overlap the scenario catalogue; extraction on real free text will be weaker.
* Novelty is validated on ~40 probes; rates are indicative.
* Resolution-time prediction explains little variance (real, heavy-tailed data).
* Contradiction detection in the Quality Manager has low precision.
* Clarification answers are mapped with rules (free text may not parse → treated as declined).
