"""HTTP API. Thin routes over backend.services.platform.Platform."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.schemas.api import (
    AnalyzeRequest, EscalateRequest, EscalationHandoffRequest, EscalationResolveRequest, EvaluateQueryRequest,
    FeedbackRequest, PostmortemRequest, ResolveRequest, ReviewRequest, SearchRequest, SimulateRequest, TriageRequest,
    TroubleshootRequest,
)
from backend.services.platform import get_platform

router = APIRouter()


def _fields(req) -> dict:
    return req.fields.model_dump(exclude_none=True) if getattr(req, "fields", None) else {}


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(404, f"not found: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# ------------------------------------------------------------------ incidents
@router.post("/incidents/search", tags=["retrieval"], summary="Hybrid retrieval (semantic + BM25 + RRF + cross-encoder)")
def search(req: SearchRequest):
    return get_platform().search(req.query, req.filters, req.top_k, req.rerank)


@router.post("/incidents/analyze", tags=["assistant"],
             summary="Full analysis via the agent graph: pattern → diagnostic (ranked top fix) → escalation if needed")
def analyze(req: AnalyzeRequest):
    return _guard(get_platform().analyze, req.text, req.title, _fields(req), req.hints, req.filters, req.incident_id, req.top_k)


@router.post("/incidents/triage", tags=["assistant"],
             summary="Classification, priority/impact/urgency, routing, tier, resolution-time and fix-accuracy")
def triage(req: TriageRequest):
    return _guard(get_platform().triage, req.text, _fields(req), req.hints, req.filters, req.incident_id, req.top_k)


@router.post("/incidents/resolve", tags=["assistant"],
             summary="Ranked single top resolution (+ fallbacks, strategy panel, LLM synthesis if available)")
def resolve(req: ResolveRequest):
    return _guard(get_platform().resolve, req.text, req.hints, req.exclude_strategies, req.filters)


@router.post("/incidents/troubleshoot", tags=["troubleshooting"],
             summary="Interactive troubleshooting: start | respond (WORKED/FAILED/UNKNOWN) | clarify | escalate | state")
def troubleshoot(req: TroubleshootRequest):
    return _guard(get_platform().troubleshoot, req)


@router.post("/incidents/feedback", tags=["feedback"], summary="Thumbs up/down + structured reasons → KB evolution")
def feedback(req: FeedbackRequest):
    return _guard(get_platform().feedback, req)


@router.post("/incidents/escalate", tags=["escalation"], summary="Build a structured escalation packet (Escalation Agent)")
def escalate(req: EscalateRequest):
    return _guard(get_platform().escalate, req)


@router.get("/escalations", tags=["escalation"], summary="Escalated incidents for L2/L3: open first, with their packets")
def escalations():
    return get_platform().escalations()


@router.post("/escalations/{escalation_id}/resolve", tags=["escalation"],
             summary="L2/L3 records what fixed an escalated incident → incident resolved → KB evolution")
def resolve_escalation(escalation_id: int, req: EscalationResolveRequest):
    return _guard(get_platform().resolve_escalation, escalation_id, req)


@router.post("/escalations/{escalation_id}/hand-off", tags=["escalation"],
             summary="Current tier passes the escalation to the next one (L2 → L3) with a note on what it tried")
def hand_off_escalation(escalation_id: int, req: EscalationHandoffRequest):
    return _guard(get_platform().hand_off_escalation, escalation_id, req)


@router.post("/incidents/simulate", tags=["correlation"], summary="Simulate incoming incidents for Live Correlation")
def simulate(req: SimulateRequest):
    return _guard(get_platform().simulate, req)


@router.get("/incidents/correlations", tags=["correlation"], summary="Live correlation window: events and alerts")
def correlations():
    return get_platform().correlations()


@router.get("/incidents/{incident_id}", tags=["incidents"], summary="Incident record with provenance, fingerprint, quality")
def get_incident(incident_id: str):
    out = get_platform().incident(incident_id)
    if out is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return out


@router.get("/incidents/{incident_id}/evidence-chain", tags=["evidence"], summary="Structured 'why this recommendation' trace")
def evidence_chain(incident_id: str):
    out = get_platform().evidence_chain(incident_id)
    if out is None:
        raise HTTPException(404, f"incident {incident_id} not found")
    return out


@router.get("/incidents/{incident_id}/attempts", tags=["troubleshooting"], summary="Formal resolution-attempt history")
def attempts(incident_id: str):
    return {"incident_id": incident_id, "attempts": get_platform().attempts(incident_id)}


# ------------------------------------------------------------------ patterns
@router.get("/patterns", tags=["patterns"], summary="Incident families, cross-symptom findings, proactive findings")
def patterns(include_emerging: bool = True):
    return get_platform().patterns(include_emerging)


@router.get("/patterns/graph", tags=["patterns"], summary="Family relationship graph (node-link JSON)")
def pattern_graph():
    return get_platform().family_graph()


@router.get("/patterns/{pattern_id}", tags=["patterns"], summary="Family detail: signature, recurrence, causal chain, strategies")
def pattern(pattern_id: str):
    out = get_platform().pattern(pattern_id)
    if out is None:
        raise HTTPException(404, f"pattern {pattern_id} not found")
    return out


# ------------------------------------------------------------------ postmortem / KB
@router.post("/postmortem", tags=["knowledge"], summary="Structured postmortem → Knowledge Base Evolution")
def postmortem(req: PostmortemRequest):
    return _guard(get_platform().postmortem, req.incident_id, req.feed_to_kb)


@router.get("/kb/quality", tags=["knowledge"], summary="Knowledge Quality Manager summary")
def kb_quality():
    return get_platform().kb_quality()


@router.get("/kb/evolution", tags=["knowledge"], summary="KB evolution audit trail, recent additions, review queue")
def kb_evolution():
    return get_platform().kb_evolution_view()


@router.post("/kb/evolve", tags=["knowledge"], summary="Run the KB evolution batch now (normally nightly)")
def kb_evolve():
    return get_platform().kb_evolve()


@router.post("/kb/review/{incident_id}", tags=["knowledge"], summary="Approve / reject a record flagged for manual review")
def kb_review(incident_id: str, req: ReviewRequest):
    return _guard(get_platform().kb_review, incident_id, req.approve, req.reviewer)


# ------------------------------------------------------------------ evaluation / health
@router.get("/evaluation", tags=["evaluation"], summary="Latest evaluation results (computed by scripts/run_evaluation.py)")
def evaluation():
    p = Path(get_platform().rt.s.evaluation_dir) / "evaluation_results.json"
    if not p.exists():
        raise HTTPException(404, "no evaluation results yet — run scripts/run_evaluation.py")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/evaluation/query", tags=["evaluation"],
             summary="Evaluate one query: how well the knowledge base can answer it (Good / Fair / Poor)")
def evaluation_query(req: EvaluateQueryRequest):
    return _guard(get_platform().evaluate_query, req.text)


@router.get("/health", tags=["system"], summary="Component status and active fallbacks")
def health():
    return get_platform().health()
