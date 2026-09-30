"""LLM guidance (step relevance, restated steps, clarifying-question wording) with a stub LLM: no network."""
from __future__ import annotations

from backend.rag.llm import parse_json_reply
from backend.services.platform import resolved_percent
from backend.troubleshooting.guidance import apply_guidance, apply_to_ranking, guide_steps, phrase_question


class StubLLM:
    available = True
    name = "stub:test"

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete_json(self, prompt, system="", max_tokens=None, purpose=""):
        self.calls += 1
        return self.reply(prompt) if callable(self.reply) else self.reply


CANDS = [
    {"strategy_key": "F1-S1", "action": "Vendor hotfix deployed", "step": "The vendor hotfix was deployed to address this issue.", "confidence": 0.4},
    {"strategy_key": "F1-S2", "action": "Restart the service", "step": "Restarted the application service; response times normal.", "confidence": 0.3},
]
ANSWER = {"steps": [
    {"id": 1, "relevant": False, "reason": "only says someone else deployed a fix", "action": "", "observe": "", "outcomes": []},
    {"id": 2, "relevant": True, "reason": "slowness after long uptime", "action": "Restart the application service.",
     "observe": "Did response times recover after the restart?", "outcomes": ["It is fast again.", "Still slow."]},
]}


def test_parse_json_reply_handles_fences_and_prose():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('Sure! {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
    assert parse_json_reply("no json here") is None


def test_irrelevant_step_is_dropped_and_relevant_one_restated():
    g = guide_steps(StubLLM(ANSWER), "system is slow", CANDS)
    kept, dropped = apply_guidance(CANDS, g)
    assert [k["strategy_key"] for k in kept] == ["F1-S2"]
    assert dropped[0]["strategy_key"] == "F1-S1" and dropped[0]["reason"]
    assert kept[0]["guidance"]["observe"].endswith("?") and len(kept[0]["guidance"]["outcomes"]) == 2
    assert kept[0]["action"] == "Restart the application service." and kept[0]["historical_action"] == "Restart the service"
    assert kept[0]["confidence"] == 0.3  # the score is never the LLM's


def test_candidates_are_split_into_parallel_chunks_and_ids_map_back():
    cands = [{"strategy_key": f"F{i}-S1", "action": f"a{i}", "step": f"note {i}", "confidence": 0.1} for i in range(1, 8)]

    def reply(prompt):  # every chunk numbers its candidates from 1; mark them all relevant
        n = prompt.count("NOTE:")
        return {"steps": [{"id": i, "relevant": True, "reason": "ok", "action": "do it", "observe": "q?", "outcomes": ["a", "b"]}
                          for i in range(1, n + 1)]}

    llm = StubLLM(reply)
    g = guide_steps(llm, "x", cands)
    assert llm.calls == 3 and set(g) == {c["strategy_key"] for c in cands}


def test_no_llm_or_unusable_reply_keeps_the_ranking_unchanged():
    ranking = {"top": CANDS[0], "alternatives": [CANDS[1]]}
    assert guide_steps(None, "x", CANDS) is None
    assert guide_steps(StubLLM(None), "x", CANDS) is None
    assert apply_to_ranking(ranking, None) is ranking


def test_question_wording_keeps_option_count_or_falls_back():
    opts = ["single user", "multiple users", "a whole team"]
    ok = phrase_question(StubLLM({"question": "Is it only you?", "options": ["Just me", "Several", "Team"], "why": "scope"}),
                         "slow", "impact_scope", "Single or multiple?", opts)
    assert ok["question"] == "Is it only you?" and ok["options"] == ["Just me", "Several", "Team"]
    wrong_count = phrase_question(StubLLM({"question": "Is it only you?", "options": ["Just me"], "why": "x"}),
                                  "slow", "impact_scope", "Single or multiple?", opts)
    assert wrong_count["options"] == opts  # option values must stay answerable
    assert phrase_question(StubLLM({"question": "no question mark", "options": opts}), "s", "f", "q?", opts) is None


def test_stars_become_percent_resolved():
    assert [resolved_percent(n) for n in (1, 2, 3, 4, 5)] == [20, 40, 60, 80, 100]
    assert resolved_percent(3.5) == 70
