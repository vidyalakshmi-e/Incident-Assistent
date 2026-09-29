# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (desktop only: no phone layout, by the owner's decision on 2026-09-28)

## Stack

Frontend: React / Next.js, chosen by the user on 2026-09-28 to replace the Streamlit UI as the primary
surface. This departs from `prompt.txt` ("Frontend: Streamlit"); the Streamlit app in `frontend/` is kept
as the spec-compliant fallback. Backend: FastAPI (`backend/`), unchanged, called over HTTP (CORS open).

## Users

Primary: evaluators (graders, judges) watching or driving the README demo walkthrough: Incident
Assistant, then Guided Troubleshooting, Novel Incidents, Live Correlation, closing the loop into the
knowledge base, then the Evaluation Dashboard. They must grasp each differentiator and each honesty
signal in one pass.

Secondary (the product's fiction and design target): L1/L2 IT support engineers in the middle of an
incident who need one evidence-backed next step, fast.

## Product Purpose

An AI-powered incident intelligence and troubleshooting platform. A free-text incident goes in; out
comes an understood, fingerprinted incident matched to a historical pattern family (or flagged as
novel), one ranked, evidence-backed first fix with a computed confidence, guided attempt-tracked
troubleshooting, escalation with full context, and a knowledge base that learns from every resolved
incident. Success: an evaluator trusts the recommendation because every claim is traceable to evidence.

## Positioning

It goes past "search similar tickets": Pattern Intelligence (families, cross-symptom root causes,
causal chains), Novel Incident Detection (a validated P(known) threshold instead of forcing a match),
Live Incident Correlation (bursts of related tickets become one possible ongoing incident) and
Resolution Strategy Intelligence (competing historical fixes with real reopen statistics). The Enriched
Fingerprint, Causal Chain, Attempt Tracking, Evidence Chain and KB Evolution are depth upgrades of those
four, never presented as separate innovations.

## Operating Context

- Runs as local processes: `uvicorn backend.main:app --port 8000` and the UI. No Docker.
- Without an LLM key the system runs in "Retrieval-only mode, LLM unavailable" and every response is
  labelled; this is the common demo state.
- Demo presets exist: the memory-leak query, novel probes (GPS time server, tape library), correlation
  presets (db-outage-burst, vpn-storm, memory-leak, unrelated-noise).

## Capabilities and Constraints

- Endpoints: analyze, search, triage, resolve, troubleshoot (start / respond / clarify / escalate),
  feedback, escalate, escalations (list / resolve), simulate, correlations, patterns (+ detail, graph), postmortem, kb quality /
  evolution / evolve / review, evaluation, health.
- About 95% of knowledge-base text is LLM-generated, conditioned on real structured fields; every such
  value is tagged `synthetic`. Provenance vocabulary: original, derived, synthetic, inferred, missing;
  causal-chain links are observed / derived / inferred and must never look alike.
- Confidence values are computed, never LLM-guessed; "insufficient evidence" is a first-class state.
- Decision support only: destructive or disruptive actions always need human confirmation.
- An escalation is answered by a person: the L2/L3 engineer records what fixed it on the Escalations page, and
  that fix goes through the same knowledge-base quality check as any other. (Added by the owner's request;
  `prompt.txt` itself only asks for the packet.)
- One ranked top fix leads; the Resolution Strategy panel shows the alternatives. Both must coexist.
- Recurrence findings are always framed "potential pattern requiring investigation".

## Brand Commitments

- Name in use: "Incident Intelligence" (Incident Intelligence Platform). No logo or visual identity
  exists; the Streamlit look is not a commitment.
- Voice: plain, precise, honest about uncertainty. Content may be rewritten for clarity (user, 2026-09-28)
  but facts, numbers and hedges stay.

## Evidence on Hand

- Real computed metrics: `data/evaluation/evaluation_results.json` (via `GET /evaluation`),
  `docs/EVALUATION.md`, `docs/DATASET_REPORT.md`, `docs/LATENCY.md`, phase checkpoints in `docs/checkpoints/`.
- Real data: 46,606 structured incidents (Source B), 150 text incidents with 7 unique texts (Source A),
  3,129 knowledge-base records, 30-31 pattern families.
- No customers, testimonials, users, or production deployments exist. Never invent them.

## Product Principles

1. Evidence before assertion: every recommendation shows where it came from.
2. One next step, alternatives on request.
3. Never blur what was observed, derived, synthesised or inferred.
4. Say "insufficient evidence" instead of inventing an answer.
5. A human confirms anything disruptive.

## Accessibility & Inclusion

No product-specific requirement established; WCAG 2.2 AA baseline (contrast, keyboard, reduced motion).
Provenance must never be encoded by colour alone (line style or label as well).
