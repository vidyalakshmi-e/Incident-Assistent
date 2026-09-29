"""Diagnostic Agent.

Scope: *what should the engineer try next?* Owns the interactive troubleshooting decision logic and
attempt tracking. Tools: resolution ranker (over retrieval results), secondary retrieval with
exclusion of failed strategies, AttemptTracker (read/write), ClarificationPolicy, synthesis +
validation (LLM, optional). It cannot build escalation packets — it requests escalation via an
A2A message.
"""
from __future__ import annotations

from backend.agents.messages import msg
from backend.rag.resolution import rank_resolutions
from backend.rag.synthesis import synthesize, validate


class DiagnosticAgent:
    name = "diagnostic_agent"
    tools = ["resolution_ranker", "secondary_retrieval(exclude failed strategies)", "attempt_tracker",
             "clarification_policy", "llm_synthesis+validation (optional)"]

    def __init__(self, rt, troubleshooting, sidx):
        self.rt = rt
        self.ts = troubleshooting
        self.sidx = sidx

    def recommend(self, state: dict) -> dict:
        """One-shot recommendation for /analyze and /resolve (no session)."""
        bundle = state["bundle"]
        ranking = rank_resolutions(bundle.retrieval.results, self.sidx, reranked=bundle.retrieval.mode.reranked,
                                   family=bundle.families[0] if bundle.families else None)
        synth = synthesize(self.rt.llm, state["text"], ranking["top"]) if ranking["top"] else None
        check = validate(self.rt.llm, self.rt.embedder, synth, ranking["top"]) if synth else None
        fam = bundle.families[0]["family_id"] if bundle.families else None
        out = {"ranking": ranking, "synthesis": synth, "validation": check,
               "strategy_panel": self.sidx.panel(fam)}
        top = ranking["top"]
        m = msg(self.name, "user", "STEP_PROPOSED" if top else "NO_EVIDENCE",
                f"Top resolution: {top['action']}" if top else "No evidence-backed resolution found",
                strategy_key=top["strategy_key"] if top else None, confidence=top["confidence"] if top else None)
        return {"diagnostic": out, "messages": [m], "route": "end" if top else "escalation"}

    def start_session(self, state: dict) -> dict:
        view = self.ts.start(state["text"], incident_id=state.get("incident_id"), hints=state.get("hints"))
        return self._route(view)

    def turn(self, state: dict) -> dict:
        t = state["turn"]
        if t["kind"] == "respond":
            view = self.ts.respond(t["session_id"], t["attempt_id"], t["response"], t.get("notes"))
        elif t["kind"] == "clarify":
            view = self.ts.clarify(t["session_id"], t.get("answer"), declined=t.get("declined", False))
        else:
            view = self.ts.escalate(t["session_id"], reason=t.get("reason", "requested by engineer"))
        return self._route(view)

    def _route(self, view: dict) -> dict:
        if view["status"] in ("escalation_requested", "novel"):
            m = msg(self.name, "escalation_agent", "ESCALATE", view.get("escalation_reason") or "novel incident",
                    session_id=view["session_id"], attempts=len(view["attempts"]),
                    clarifications=len(view["clarifications"]))
            return {"session": view, "messages": [m], "route": "escalation"}
        intent = {"active": "STEP_PROPOSED", "awaiting_clarification": "CLARIFICATION_ASKED",
                  "resolved": "RESOLVED"}.get(view["status"], view["status"].upper())
        m = msg(self.name, "user", intent, f"session {view['session_id']} → {view['status']}",
                round=view["round"], session_id=view["session_id"])
        return {"session": view, "messages": [m], "route": "end"}
