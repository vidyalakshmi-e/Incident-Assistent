# Incident Intelligence Platform
Github link: https://github.com/vidyalakshmi-e/Incident-Assistent

**An AI-powered Incident Intelligence and Troubleshooting platform** that combines hybrid retrieval with
historical incident pattern discovery (including causal-chain reasoning), novel-incident detection,
live incident correlation, resolution intelligence, transparent evidence-backed recommendations, and a
knowledge base that evolves from every resolved incident.

```
Traditional:  Incident → Search → Similar tickets → Answer
This system:  Incident → Understand → Enriched fingerprint → Pattern + causal chain → Known vs. novel
              → Historical resolution strategies → Ranked top fix with full evidence trail
              → Guided, attempt-tracked troubleshooting → Detect related ongoing incidents
              → Escalate with complete context → Postmortem → Feed validated knowledge back in
```

The four differentiators: **Pattern Intelligence** (with causal chains), **Novel Incident Detection**,
**Live Incident Correlation**, and **Resolution Strategy Intelligence**. Each is deepened by the Enriched
Fingerprint, Resolution Attempt Tracking, the Evidence Chain and Knowledge Base Evolution.

**For the talk:** [`presentation/presentation_guide.md`](presentation/presentation_guide.md) explains how every stage works, why it was built that way, how the app runs with no API key, and how it was evaluated. [`presentation/file_guide.md`](presentation/file_guide.md) says what each file does.

---

## Quick start (local)

Requirements: Python 3.10+. A GPU is optional; everything runs on CPU, just more slowly.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# edit .env                          # optionally set LLM_API_KEY; blank = retrieval-only mode

# The processed artefacts are already in data/. To rebuild everything from the raw files:
python scripts/build_all.py          # dataset → index → patterns → models → calibration (~4 min on a GPU)
python scripts/run_evaluation.py     # all metrics → data/evaluation/evaluation_results.json
python scripts/export_training_data.py   # the rows the models were trained on → data/training/*.csv

# run the platform
uvicorn backend.main:app --port 8000             # API + Swagger UI at http://localhost:8000/docs
cd web && npm install && npm run dev             # UI at http://localhost:3000 (Next.js, primary)
streamlit run frontend/app.py                    # legacy Streamlit UI at http://localhost:8501
```

The raw data lives in `data/raw/`. Note that `incidents_text.csv` is the *structured* event log and
`incidents_structured.xlsx` is the *text-rich* file; the pipeline detects each source by its content, not its name.

On a build with no cache and no GPU, `build_dataset.py` reuses the cached LLM text
(`data/processed/synthetic_text_cache.jsonl`), so the dataset rebuilds identically. To regenerate that
text with a local LLM, run `python scripts/build_dataset.py --generator llm`.

## Services

The platform runs as separate local processes, each started from the project root:
- **API**: `uvicorn backend.main:app --port 8000`. FastAPI with the agents and intelligence.
- **UI**: `cd web && npm run dev` (Node 20.9+). The Next.js frontend (see `web/README.md`); it proxies `/api/*` to `API_URL`. Desktop only: there is no phone layout.
- **Legacy UI** (optional): `streamlit run frontend/app.py`. The original Streamlit frontend, kept because `prompt.txt` specifies Streamlit. It has no Escalations page.
- **KB worker** (optional): `python scripts/kb_evolution_batch.py --loop`. The nightly Knowledge-Base-Evolution batch; the API also processes resolved incidents on demand.
- **Vector DB**: embedded ChromaDB in `vectorstore/` by default. To use a Chroma server instead, run `chroma run --path vectorstore_server --port 8001` and set `CHROMA_MODE=http`. On start-up the API fills an empty server from the prebuilt embeddings.

Run the API and a worker against the same embedded store one at a time, or switch to a Chroma server; embedded ChromaDB isn't safe for concurrent writers.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_API_KEY` | *(blank)* | Leaving it blank gives **"Retrieval-only mode — LLM unavailable"**: no crash, and every response is labelled. A value that is not a plausible key (spaces, non-ASCII, a pasted comment) is treated as unset. A key that keeps failing is reported in `/health` and also falls back |
| `LLM_MODEL` | `gpt-4o-mini` | Any model served by the configured endpoint. **Leave it blank for a gateway that picks the model itself** (the lab gateway `https://keygateway1.arshnivlabs.com/v1`): no `model` is sent. That gateway also caps `max_tokens` at 500 (`LLM_MAX_TOKENS_CAP`) |
| `LLM_PROVIDER` | `openai` | `openai` (any OpenAI-compatible endpoint: OpenAI, NVIDIA NIM, Ollama, LM Studio), `local` (an in-process Hugging Face model), or `none` |
| `LLM_BASE_URL` | OpenAI | Set this when the key belongs to a gateway or another provider, e.g. `https://integrate.api.nvidia.com/v1` or `http://localhost:11434/v1`. Keep `.env` comments on their own line: a `#` right after `=` becomes part of the value |
| `EMBEDDING_PROVIDER` | `local` | `local` (all-MiniLM-L6-v2), `openai`, or `nvidia`. If the chosen provider fails, it falls back to local automatically and logs the switch |
| `RERANKER_PROVIDER` | `local` | `local` (ms-marco-MiniLM-L-6-v2), `nvidia`, or `none`. The fallback chain is local, then unreranked (labelled) |
| `ESCALATION_TIERS` | `L1,L2,L3` | Tier **order** is configurable, so the direction can be confirmed against the grading rubric |
| `CHROMA_MODE` | `embedded` | `embedded` (the `vectorstore/` folder) or `http` (a Chroma server) |

## Demo walkthrough

1. **Incident Assistant.** Enter *"The application is becoming slower and sometimes freezes when users try to
   open records. Restarting fixes it temporarily."* The assistant then works through these steps:
   - query understanding (vague → technical, e.g. "restarting fixes it temporarily" → memory leak / resource exhaustion);
   - hybrid retrieval and matching to the *memory leak / heap exhaustion* family;
   - one ranked top fix, with a computed confidence.

   A one-line **Query evaluation** (Good / Fair / Poor) sits under the verdict. Expand **"Why did the
   system recommend this?"** for the Evidence Chain.
2. **Guided Troubleshooting.** Start from the assistant and mark the restart as **FAILED**. The system
   records the attempt, excludes that approach and suggests the next-best one. Fail the remaining steps:
   before escalating it asks one clarifying question, then builds an **escalation packet** with the full
   attempt history and the clarification notes. Open **Escalations**: this is where the L2/L3 engineer
   reads the packet and either records what fixed it or **hands it up to L3** with a note. That fix goes
   through the same knowledge-base quality check as any other, so an escalated incident can still become knowledge.
3. **Novel Incidents.** Try *"The GPS time server lost satellite lock and trading hosts drift from UTC"*.
   The result is **NOVEL INCIDENT**, showing P(known) against the validated threshold.
4. **Close the loop.** Start a new troubleshooting session and mark the first step **WORKED**. Then click
   *Generate postmortem + update KB*, or submit feedback. Open **Knowledge base**: the incident now
   appears as new knowledge with its provenance, and it is retrievable.
5. **Query Evaluation.** Every query gets its own evaluation. Try the *Relevant* example (Good), then
   *Unrelated* or *Gibberish* (Poor). Queries analysed in the Assistant are listed there too.

The whole-application metrics are still computed by `scripts/run_evaluation.py` into
`data/evaluation/evaluation_results.json` and served at `GET /evaluation`; the web UI no longer shows them.

Sample queries for the API (Swagger) or the UI:

| Query | Expected behaviour |
|---|---|
| `the system feels slow and basic things take forever` | Vague query: a clarification may be asked; retrieves the performance families |
| `Users are sent back to the login page after entering credentials` | SSO / directory-sync family |
| `Reports keep loading forever and then fail with a timeout during the morning peak` | DB slow-query or connection-pool families |
| `Nothing comes out of the printer, documents stay in the queue` | Printer spooler family |
| `Robotic tape library arm is jammed` | NOVEL INCIDENT |

## API (FastAPI, OpenAPI at `/docs`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/incidents/search` | Hybrid retrieval with filters and why-retrieved, plus fingerprint, families, novelty and Evidence Chain |
| POST | `/incidents/analyze` | Agent graph (pattern → diagnostic → escalation): ranked top fix, strategy panel, Evidence Chain, A2A messages |
| POST | `/incidents/triage` | Classification, priority/impact/urgency, team and tier routing, resolution-time prediction, fix accuracy |
| POST | `/incidents/resolve` | Top resolution plus fallbacks (`exclude_strategies`), LLM synthesis and validation when available |
| POST | `/incidents/troubleshoot` | `action`: start / respond (WORKED, FAILED, UNKNOWN) / clarify / escalate / state |
| POST | `/incidents/feedback` | Thumbs up/down, structured reasons and 4 questions; a negative rating lowers the influence of the supporting records (saved), and a resolved incident triggers KB evolution |
| POST | `/incidents/escalate` | Structured escalation packet (Escalation Agent) |
| GET | `/escalations` | Escalated incidents for L2/L3, open first, each with its packet and resolution |
| POST | `/escalations/{id}/resolve` | L2/L3 records what fixed it: the incident is resolved and goes through KB evolution |
| POST | `/escalations/{id}/hand-off` | The current tier passes the escalation to the next one (L2 → L3) with a note; the old one stays as history |
| POST | `/incidents/simulate` | Simulate incoming incidents for Live Correlation |
| GET | `/incidents/correlations` | Current correlation window: events and alerts |
| GET | `/incidents/{id}` | Record with field-level provenance, fingerprint, quality, family, causal chain. Works for live incidents and for historical knowledge-base incidents |
| GET | `/incidents/{id}/evidence-chain` | Structured "why this recommendation" trace |
| GET | `/incidents/{id}/attempts` | Formal resolution-attempt history |
| GET | `/patterns`, `/patterns/{id}`, `/patterns/graph` | Families, cross-symptom findings, proactive findings, recurrence, causal chains, strategies, graph |
| POST | `/postmortem` | Structured postmortem, then KB evolution |
| GET | `/kb/quality`, `/kb/evolution`; POST `/kb/evolve`, `/kb/review/{id}` | Knowledge quality, evolution audit trail, batch run, manual review |
| POST | `/evaluation/query` | Evaluate one query: score, Good / Fair / Poor and the four signals behind it (`/incidents/analyze` returns the same as `query_evaluation`) |
| GET | `/evaluation`, `/health` | Latest whole-application metrics; component status and active fallbacks |

## Tests

```bash
pytest -m "not integration"   # unit tests, no models needed (~3 s)
pytest                        # + integration tests (retrieval, all fallbacks, API, troubleshooting, KB evolution, reproducibility)
```

## Project structure

```
backend/
  main.py                 FastAPI app          api/        routes
  config/                 settings, taxonomy, rule lexicons
  data_pipeline/          loaders, profiling, cleaning, transform, scenarios, conditioned synthetic text, chunking
  knowledge/              quality manager, indexer, KB evolution
  retrieval/              embeddings, reranker, ChromaDB, BM25, query understanding, hybrid retrieval
  intelligence/           fingerprinting, pattern_detection, causal_chain, novelty, correlation, recurrence, graph
  rag/                    llm client, resolution ranking, strategy intelligence, synthesis+validation, guardrails
  troubleshooting/        session loop, attempt tracking, clarification
  agents/                 LangGraph agents (pattern, diagnostic, escalation) + A2A messages
  evidence/               Evidence Chain assembly
  services/               platform facade, analysis pipeline, triage, escalation, postmortem, runtime
  evaluation/             query generator, calibration, metrics, suite, model training
  models/ database/ schemas/
web/                      Next.js UI (primary): src/app routes, src/components
frontend/app.py + views/  Streamlit UI (legacy, 8 screens)
scripts/                  build_*.py, calibrate.py, train_models.py, run_evaluation.py, kb_evolution_batch.py
data/raw | processed | evaluation
tests/
presentation/             presentation_guide.md (talk guide) and file_guide.md (what each file does)
requirements.txt, .env
```

## Honesty notes

- About 95% of the knowledge-base text is LLM-generated. It is conditioned on real structured fields and every generated value is flagged `synthetic`. The only real free text is Source A (150 rows, 7 unique texts). See `data/processed/dataset_report.json` for the exact ratios.
- All reported numbers are computed by `scripts/run_evaluation.py`. Relevance labels come from the generator's ground truth, not from the system being evaluated.
- The system is decision support: destructive actions always require human confirmation, and feedback changes knowledge records but does not retrain any model.
