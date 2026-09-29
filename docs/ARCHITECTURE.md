# Architecture

The architecture is expressed as renderable **Mermaid** diagrams (GitHub, GitLab, VS Code and most
Markdown viewers render them). Every box maps to a module; the table under each diagram gives the path.

## 1. End-to-end intelligence flow

```mermaid
flowchart TD
    %% ---------------- offline build ----------------
    subgraph OFFLINE["Offline build (scripts/build_all.py)"]
        A1[("Source A · text-rich<br/>incidents_structured.xlsx<br/>150 rows")]
        A2[("Source B · structured event log<br/>incidents_text.csv<br/>46,606 rows")]
        P1["Preprocessing & merge<br/>content-based source detection · day-first timestamps<br/>placeholder normalisation · no forced join"]
        P2["Conditioned synthetic text<br/>(local LLM, conditioned on real CI / Impact / Closure / Reassignments)<br/>field-level provenance"]
        Q["Knowledge Quality Manager<br/>generic notes · duplicates · contradictions · quality score"]
        F["Enriched fingerprint<br/>component · service · symptom · failure type · trigger<br/>root cause · environment · dependency · business impact · scope"]
        PI["Pattern Intelligence Engine<br/>families · cross-symptom root causes · recurrence<br/>+ Causal Chain (observed / derived / inferred)"]
        G["Relationship graph<br/>same CI · KB article · change · near-duplicate · family"]
        RS["Resolution strategies per family<br/>(outcome stats only where real data supports them)"]
        E["Embeddings<br/>all-MiniLM-L6-v2 (local default)"]
        V[("ChromaDB<br/>vectors")]
        B[("BM25 index")]
        SQL[("SQLite · SQLAlchemy<br/>incidents · fingerprints · patterns · chains<br/>attempts · feedback · escalations · postmortems")]
        A1 --> P1
        A2 --> P1 --> P2 --> Q --> F --> PI --> G
        PI --> RS
        Q --> E --> V
        Q --> B
        PI --> SQL
        G --> SQL
    end

    %% ---------------- online ----------------
    subgraph ONLINE["Online (FastAPI + LangGraph agents)"]
        IN(["Engineer describes an incident"])
        QU["Query understanding<br/>vague → technical translation"]
        HR["Hybrid retrieval<br/>semantic + BM25 → Reciprocal Rank Fusion<br/>metadata filters · duplicate collapsing"]
        RR["Cross-encoder reranking<br/>(calibrated relevance)"]
        QF["Incident fingerprint"]
        FM["Family match<br/>(retrieval evidence × centroid)"]
        ND{"Novelty detection<br/>P(known) ≥ validated threshold?"}
        NOV["NOVEL INCIDENT<br/>fresh investigation"]
        RA["Resolution assistance<br/>ONE ranked top pick (real confidence)<br/>+ separate strategy panel"]
        TS["Interactive troubleshooting<br/>formal attempt tracking · exclusion of failed approaches<br/>clarification before escalation"]
        TR["Triage & escalation<br/>classification · priority · routing · L1→L2→L3 (configurable)<br/>resolution-time · fix-accuracy"]
        EC[["Evidence Chain<br/>attached to every recommendation"]]
        FB["Feedback<br/>👍/👎 + reasons + 4 questions"]
        PM["Postmortem"]
        KE["Knowledge Base Evolution<br/>re-score → index · or manual review"]
        IN --> QU --> HR --> RR --> FM
        QU --> QF --> FM
        FM --> ND
        ND -- known --> RA --> TS
        ND -- novel --> NOV --> TR
        TS -- WORKED --> FB
        TS -- "round cap / no step" --> TR
        TR --> FB
        FB --> KE
        TS --> PM --> KE
        RA -.-> EC
        TR -.-> EC
        ND -.-> EC
        FM -.-> EC
    end

    %% ---------------- live correlation stream ----------------
    subgraph LIVE["Live incident stream"]
        LS(["Incoming tickets<br/>(or 'Simulate Incoming Incident')"])
        LC["Live Correlation<br/>sliding window · shared family / near-identical text"]
        AL["Alert: possible single ongoing incident"]
        LS --> LC --> AL
    end

    V --> HR
    B --> HR
    SQL --> FM
    RS --> RA
    PI --> FM
    PI --> LC
    HR --> LC
    AL --> TR
    KE -- "embedding + BM25 + family + graph update" --> V
    KE --> B
    KE --> SQL
    KE --> PI
```

| Box | Code |
|---|---|
| Preprocessing & merge | `backend/data_pipeline/{loaders,cleaning,transform,build}.py` |
| Conditioned synthetic text | `backend/data_pipeline/{scenarios,synthetic,llm_verbalizer}.py` |
| Knowledge Quality Manager | `backend/knowledge/quality.py` |
| Enriched fingerprint | `backend/intelligence/fingerprinting.py`, lexicons in `backend/config/lexicon.py` |
| Pattern Intelligence Engine | `backend/intelligence/{pattern_detection,recurrence,causal_chain,builder}.py` |
| Relationship graph | `backend/intelligence/graph.py` |
| Resolution strategies | `backend/rag/strategy.py` |
| Embeddings / ChromaDB / BM25 | `backend/retrieval/{embeddings,vector_store,bm25_index}.py` |
| Query understanding | `backend/retrieval/query_understanding.py` |
| Hybrid retrieval + reranking | `backend/retrieval/{hybrid,reranker}.py` |
| Novelty detection | `backend/intelligence/novelty.py`, threshold fit in `backend/evaluation/calibration.py` |
| Resolution assistance | `backend/rag/{resolution,guardrails,synthesis}.py` |
| Interactive troubleshooting | `backend/troubleshooting/{session,attempts,clarification}.py` |
| Triage & escalation | `backend/services/{triage,escalation}.py` |
| Evidence Chain | `backend/evidence/chain.py` |
| Feedback / KB Evolution / Postmortem | `backend/knowledge/evolution.py`, `backend/services/postmortem.py` |
| Live correlation | `backend/intelligence/correlation.py` |

## 2. Agent graph (LangGraph)

Three agents with **different tool sets**. Every hand-off is an explicit A2A message
(`backend/agents/messages.py`) that the API returns as `agent_messages`.

```mermaid
flowchart LR
    S((START)) --> PA
    subgraph PA["Pattern Intelligence Agent"]
        pa1[hybrid retrieval · read-only]
        pa2[fingerprinter]
        pa3[pattern engine match]
        pa4[causal-chain store]
        pa5[novelty detector]
    end
    subgraph DA["Diagnostic Agent"]
        da1[resolution ranker]
        da2[secondary retrieval<br/>excluding failed strategies]
        da3[attempt tracker · write]
        da4[clarification policy]
        da5[LLM synthesis + validation · optional]
    end
    subgraph EA["Escalation Agent"]
        ea1[triage models]
        ea2[tier router · configurable order]
        ea3[team / expertise router]
        ea4[escalation records · write]
    end
    PA -- "PATTERN_CONTEXT (known)" --> DA
    PA -- "NOVEL_INCIDENT" --> EA
    DA -- "STEP_PROPOSED / CLARIFICATION_ASKED / RESOLVED" --> E((END))
    DA -- "ESCALATE (round cap, no evidence, declined)" --> EA
    EA -- "PACKET_READY" --> E
```

Graphs compiled in `backend/agents/graph.py`: `analyze` (pattern → diagnostic → escalation?),
`session` (diagnostic start → escalation?), `turn` (diagnostic turn → escalation?), `escalate`.

## 3. Troubleshooting loop with clarification before escalation

```mermaid
stateDiagram-v2
    [*] --> Analyse
    Analyse --> Novel: P(known) < threshold
    Analyse --> AskClarification: low confidence AND vague<br/>or two families within margin
    Analyse --> SuggestStep
    AskClarification --> Analyse: answer updates fingerprint / hints
    AskClarification --> SuggestStep: declined
    SuggestStep --> Resolved: WORKED
    SuggestStep --> SuggestStep: FAILED → exclude strategy (+ near-identical actions)<br/>secondary retrieval → next-best
    SuggestStep --> PreEscalationCheck: round cap reached / no evidence-backed step
    PreEscalationCheck --> AskClarification: a missing field could sharpen one more step<br/>(max 1 question per session)
    PreEscalationCheck --> Escalated: nothing useful to ask
    Novel --> Escalated: fresh investigation
    Resolved --> KBEvolution: feedback / postmortem
    Escalated --> [*]
    KBEvolution --> [*]
```

## 4. Deployment (local processes)

```mermaid
flowchart LR
    U((Engineer)) --> UI["ui · Streamlit :8501"]
    UI -- REST --> API["api · FastAPI :8000<br/>agents · retrieval · intelligence"]
    API --> CH[("ChromaDB<br/>embedded vectorstore/ (default)<br/>or chroma run :8001 (CHROMA_MODE=http)")]
    API --> DB[("data/processed<br/>SQLite + artefacts")]
    W["kb-worker · kb_evolution_batch.py --loop<br/>(optional nightly batch)"] --> CH
    W --> DB
    API -. optional .-> LLM["LLM endpoint<br/>(OpenAI-compatible, if LLM_API_KEY)"]
```
