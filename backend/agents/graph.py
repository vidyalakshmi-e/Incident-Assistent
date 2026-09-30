"""LangGraph orchestration of the three agents.

    analyze:   START → pattern_intelligence ─┬─(known)→ diagnostic ─┬─(step found)→ END
                                             └─(novel)→ escalation ←─┘(no evidence)   → END
    session:   START → diagnostic(start) ─┬─→ END
                                          └─(novel / escalation requested)→ escalation → END
    turn:      START → diagnostic(turn)  ─┬─→ END
                                          └─(round cap / no step / declined)→ escalation → END

Each node is a different agent with a different tool set (see the agent modules); routing is a
conditional edge on the agent's output, and every hand-off is recorded as an A2A message.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from backend.agents.diagnostic_agent import DiagnosticAgent
from backend.agents.escalation_agent import EscalationAgent
from backend.agents.pattern_agent import PatternIntelligenceAgent
from backend.rag.strategy import StrategyIndex
from backend.troubleshooting.session import TroubleshootingService


class AgentState(TypedDict, total=False):
    text: str
    hints: dict
    filters: Any
    fields: dict
    incident_id: str | None
    top_k: int
    pool: int | None
    persist_escalation: bool
    escalation_reason: str
    turn: dict
    bundle: Any
    pattern: dict
    diagnostic: dict
    session: dict
    escalation: dict
    route: str
    messages: Annotated[list, operator.add]


def _route(state: AgentState) -> str:
    return state.get("route", "end")


class AgentOrchestrator:
    def __init__(self, rt):
        self.rt = rt
        self.sidx = StrategyIndex.load(rt.s.processed_dir)
        self.troubleshooting = TroubleshootingService(rt, self.sidx)  # no builder → escalation goes through the graph
        self.pattern_agent = PatternIntelligenceAgent(rt)
        self.diagnostic_agent = DiagnosticAgent(rt, self.troubleshooting, self.sidx)
        self.escalation_agent = EscalationAgent(rt, self.troubleshooting)
        self.analyze_graph = self._build_analyze()
        self.session_graph = self._build_single("diagnostic_start", self.diagnostic_agent.start_session)
        self.turn_graph = self._build_single("diagnostic_turn", self.diagnostic_agent.turn)
        self.escalate_graph = self._build_escalate()

    def _build_analyze(self):
        g = StateGraph(AgentState)
        g.add_node("pattern_intelligence", self.pattern_agent.run)
        g.add_node("diagnostic", self.diagnostic_agent.recommend)
        g.add_node("escalation", self.escalation_agent.run)
        g.add_edge(START, "pattern_intelligence")
        g.add_conditional_edges("pattern_intelligence", _route, {"diagnostic": "diagnostic", "escalation": "escalation"})
        g.add_conditional_edges("diagnostic", _route, {"end": END, "escalation": "escalation"})
        g.add_edge("escalation", END)
        return g.compile()

    def _build_single(self, name: str, fn):
        g = StateGraph(AgentState)
        g.add_node(name, fn)
        g.add_node("escalation", self.escalation_agent.run)
        g.add_edge(START, name)
        g.add_conditional_edges(name, _route, {"end": END, "escalation": "escalation"})
        g.add_edge("escalation", END)
        return g.compile()

    def _build_escalate(self):
        g = StateGraph(AgentState)
        g.add_node("pattern_intelligence", self.pattern_agent.run)
        g.add_node("escalation", self.escalation_agent.run)
        g.add_edge(START, "pattern_intelligence")
        g.add_edge("pattern_intelligence", "escalation")
        g.add_edge("escalation", END)
        return g.compile()

    # ------------------------------------------------------------------ entry points
    def analyze(self, text: str, hints: dict | None = None, filters=None, incident_id: str | None = None,
                fields: dict | None = None, top_k: int = 10, pool: int | None = None) -> dict:
        return self.analyze_graph.invoke({"text": text, "hints": hints or {}, "filters": filters, "fields": fields or {},
                                          "incident_id": incident_id, "top_k": top_k, "pool": pool, "messages": []})

    def start_session(self, text: str, incident_id: str | None = None, hints: dict | None = None) -> dict:
        return self.session_graph.invoke({"text": text, "incident_id": incident_id, "hints": hints or {}, "messages": []})

    def turn(self, turn: dict) -> dict:
        return self.turn_graph.invoke({"turn": turn, "messages": []})

    def escalate(self, text: str, incident_id: str | None, reason: str, hints: dict | None = None,
                 fields: dict | None = None) -> dict:
        return self.escalate_graph.invoke({"text": text, "incident_id": incident_id, "hints": hints or {},
                                           "fields": fields or {}, "persist_escalation": True,
                                           "escalation_reason": reason, "messages": []})
