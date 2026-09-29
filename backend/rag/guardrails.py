"""Safety guardrails.

The system is a decision-support tool, not an autonomous administrator:
  * destructive actions (data loss risk) need ≥ 2 independent historical sources to be recommended
    at all, and are always marked "requires human confirmation"
  * disruptive actions (restarts, failovers) carry a change-window / confirmation note
  * any recommendation without retrieval grounding is flagged as unsupported
"""
from __future__ import annotations

import re

DESTRUCTIVE = re.compile(
    r"\b(delet\w*|drop (?:table|database|schema)|truncat\w*|format\w*|wip(?:e|ed|ing)|reimag\w*|rm -rf|"
    r"restor\w* .{0,30}(?:from|backup)|purg\w*|kill\w* .{0,20}(?:session|process)|terminat\w* .{0,20}session|"
    r"factory reset|reinstall(?:ed)? (?:the )?(?:os|operating system)|archiv\w* or delet\w*)", re.I)
DISRUPTIVE = re.compile(r"\b(restart\w*|reboot\w*|recycl\w*|power-cycl\w*|fail(?:ed)? ?over|roll(?:ed)? ?back|"
                        r"rollback|drain\w*|maintenance mode)", re.I)
MIN_SOURCES_FOR_DESTRUCTIVE = 2


def classify_action(text: str) -> dict:
    d = DESTRUCTIVE.search(text or "")
    r = DISRUPTIVE.search(text or "")
    return {"destructive": bool(d), "destructive_phrase": d.group(0) if d else None,
            "disruptive": bool(r), "disruptive_phrase": r.group(0) if r else None}


def safety_review(text: str, n_independent_sources: int) -> dict:
    c = classify_action(text)
    notes, allowed = [], True
    if c["destructive"]:
        if n_independent_sources < MIN_SOURCES_FOR_DESTRUCTIVE:
            allowed = False
            notes.append(f"Destructive action ('{c['destructive_phrase']}') backed by only {n_independent_sources} "
                         f"historical source(s) (< {MIN_SOURCES_FOR_DESTRUCTIVE}) — not recommended; escalate instead.")
        else:
            notes.append(f"Destructive action ('{c['destructive_phrase']}'): requires explicit human confirmation "
                         "and a verified backup before execution.")
    if c["disruptive"]:
        notes.append(f"Disruptive action ('{c['disruptive_phrase']}'): perform in an agreed window / confirm impact "
                     "with the service owner.")
    if n_independent_sources == 0:
        allowed = False
        notes.append("No historical grounding for this action — flagged as unsupported.")
    return {**c, "allowed": allowed, "requires_human_confirmation": c["destructive"] or c["disruptive"],
            "notes": notes, "independent_sources": n_independent_sources}
