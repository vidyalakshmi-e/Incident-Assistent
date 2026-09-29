"""Escalation Agent.

Scope: *who should take over, with what context?* Tools: triage models (priority / category
classifiers, resolution-time prediction), tier router (configurable L1→L2→L3 order), team /
expertise router, escalation-record store (SQL write), attempt history (read-only). It never
proposes fixes itself — it packages the Diagnostic Agent's history.
"""
from __future__ import annotations

from backend.agents.messages import msg
from backend.services.analysis import analyze_text
from backend.services.escalation import build_packet


class EscalationAgent:
    name = "escalation_agent"
    tools = ["triage_models", "tier_router(configurable order)", "team_router", "escalation_record_store",
             "attempt_history(read-only)"]

    def __init__(self, rt, troubleshooting):
        self.rt = rt
        self.ts = troubleshooting

    def run(self, state: dict) -> dict:
        session = state.get("session")
        if session:  # hand-off from a troubleshooting session
            ctx = self.ts.session_context(session["session_id"])
            st = ctx["state"]
            bundle = analyze_text(self.rt, ctx["query_text"], hints=st.get("hints", {}))
            reason = st.get("escalation_reason") or ("novel incident — fresh investigation" if session["status"] == "novel"
                                                     else "requested")
            packet = build_packet(self.rt, incident_id=ctx["incident_id"], text=ctx["query_text"], reason=reason,
                                  bundle=bundle, attempts=session["attempts"], clarifications=st.get("clarifications", []),
                                  session_id=ctx["session_id"], remaining_alternatives=st.get("alternatives", []))
            view = self.ts.finalize_escalation(ctx["session_id"], packet)
            m = msg(self.name, "user", "PACKET_READY", f"Escalated to {packet['tier']} / {packet['suggested_team']}",
                    packet_id=packet["packet_id"], tier=packet["tier"])
            return {"session": view, "escalation": packet, "messages": [m], "route": "end"}
        # one-shot (novel incident from /analyze, or explicit /escalate without a session)
        bundle = state.get("bundle") or analyze_text(self.rt, state["text"], hints=state.get("hints"))
        persist = bool(state.get("persist_escalation"))
        reason = state.get("escalation_reason") or ("novel incident — no historical match; fresh investigation"
                                                    if bundle.novelty.get("is_novel") else "requested")
        alts = []
        diag = state.get("diagnostic")
        if diag and diag.get("ranking"):
            r = diag["ranking"]
            alts = ([r["top"]] if r["top"] else []) + r["alternatives"]
        packet = build_packet(self.rt, incident_id=state.get("incident_id") or "unassigned", text=state["text"],
                              reason=reason, bundle=bundle, remaining_alternatives=alts,
                              fields=state.get("fields"), persist=persist)
        m = msg(self.name, "user", "PACKET_READY" if persist else "ROUTING_PROPOSED",
                f"{'Escalated' if persist else 'Proposed routing'}: {packet['tier']} / {packet['suggested_team']}",
                packet_id=packet["packet_id"], tier=packet["tier"])
        return {"escalation": packet, "messages": [m], "route": "end"}
