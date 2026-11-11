"""Unit tests for the eval harness itself. The model is mocked: no credit is spent here."""

import asyncio
import json

import pytest
from claude_agent_sdk import ResultMessage, StreamEvent

from app.core import llm, store
from evals import harness
from evals.harness import Case, Run


def text_delta(text: str) -> StreamEvent:
    return StreamEvent(
        uuid="u", session_id="s", event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}
    )


def tool_start(name: str) -> StreamEvent:
    return StreamEvent(
        uuid="u", session_id="s", event={"type": "content_block_start", "content_block": {"type": "tool_use", "name": name}}
    )


def result(is_error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=is_error, num_turns=1, session_id="s",
        result="plan limit" if is_error else "ok",
    )


def fake_query(messages, prompts):
    async def _query(prompt, options):
        prompts.append(prompt)
        for message in messages:
            yield message

    return _query


def fake_complete(reply, prompts=None):
    async def _complete(system_prompt, prompt):
        if prompts is not None:
            prompts.append(prompt)
        return reply

    return _complete


CASE = Case(
    id="demo",
    agent_id="content",
    profile=[("location", "Barcelona"), ("skills", "Python and FastAPI")],
    turns=["Draft a post.", "Shorter."],
    criteria=["Uses only facts from the profile.", "No emojis."],
)


def a_run(**changes) -> Run:
    return Run(**{"case": CASE, "replies": ["A post."], "tools": [], "errors": [], "board": {}, **changes})


def test_run_case_seeds_the_profile_and_sends_every_turn(monkeypatch):
    prompts: list[str] = []
    stream = [text_delta("Here it is."), tool_start("mcp__office__save_draft"), result()]
    monkeypatch.setattr(llm, "query", fake_query(stream, prompts))

    run = harness.run_case(CASE)

    assert "(location) Barcelona" in prompts[0] and prompts[0].endswith("Draft a post.")
    assert prompts[1] == "Shorter."
    assert run.replies == ["Here it is.", "Here it is."]
    assert run.tools == ["save_draft", "save_draft"]
    assert run.errors == []


def test_run_case_snapshots_what_the_agent_saved(monkeypatch):
    monkeypatch.setattr(llm, "query", fake_query([text_delta("ok"), result()], []))
    store.add_outreach(
        {"job_id": None, "target": "Hiring manager", "how_to_find": "", "message": "Hello"}, "scout"
    )

    run = harness.run_case(CASE)

    assert [note["message"] for note in run.board["outreach"]] == ["Hello"]
    assert run.board["drafts"] == []


def test_run_case_reports_agent_errors(monkeypatch):
    monkeypatch.setattr(llm, "query", fake_query([result(is_error=True)], []))

    assert harness.run_case(CASE).errors == ["plan limit", "plan limit"]


def test_judge_prompt_holds_profile_criteria_reply_and_board():
    run = a_run(replies=["Barcelona post"], tools=["save_draft"], board={"drafts": [{"title": "T", "body": "B"}]})

    prompt = harness.judge_prompt(run)

    assert "(location) Barcelona" in prompt
    assert "1. Uses only facts from the profile." in prompt and "2. No emojis." in prompt
    assert "Barcelona post" in prompt
    assert '"title": "T"' in prompt and "save_draft" in prompt


def verdict_json(*passes: bool) -> str:
    return json.dumps(
        {"criteria": [{"criterion": i + 1, "pass": ok, "reason": f"reason {i + 1}"} for i, ok in enumerate(passes)]}
    )


def test_verdict_passes_only_when_every_criterion_passes():
    assert harness.parse_verdict(verdict_json(True, True), 2) == []
    assert harness.parse_verdict(verdict_json(True, False), 2) == ["Criterion 2 failed: reason 2"]


def test_verdict_is_read_from_a_fenced_or_chatty_reply():
    reply = f"Here is my verdict:\n```json\n{verdict_json(True, True)}\n```\nDone."
    assert harness.parse_verdict(reply, 2) == []


@pytest.mark.parametrize("reply", ["I think it is fine.", "{not json}", verdict_json(True)])
def test_unreadable_or_incomplete_verdict_fails(reply):
    failures = harness.parse_verdict(reply, 2)
    assert len(failures) == 1 and failures[0].startswith("Judge")


def test_evaluate_combines_checks_and_judge(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(llm, "complete", fake_complete(verdict_json(True, False), prompts))
    case = Case(**{**CASE.__dict__, "checks": [harness.saved("drafts")]})

    failures = asyncio.run(harness.evaluate(a_run(case=case, board={"drafts": []})))

    assert failures == ["Nothing was saved to drafts.", "Criterion 2 failed: reason 2"]
    assert len(prompts) == 1


def test_evaluate_skips_the_judge_when_the_agent_errored(monkeypatch):
    prompts: list[str] = []
    monkeypatch.setattr(llm, "complete", fake_complete(verdict_json(True, True), prompts))

    failures = asyncio.run(harness.evaluate(a_run(errors=["plan limit"])))

    assert failures == ["Agent error: plan limit"]
    assert prompts == []


def test_built_in_checks():
    long_note = {"message": "x" * 301}
    assert harness.saved("drafts")(a_run(board={"drafts": [{"id": 1}]})) is None
    assert harness.used_tool("record_answer")(a_run(tools=["save_draft"])) == "Never called record_answer."
    assert harness.outreach_fits_linkedin(a_run(board={"outreach": [long_note]})) == "An outreach note is 301 characters (limit 300)."
    assert harness.outreach_fits_linkedin(a_run(board={"outreach": [{"message": "hi"}]})) is None
    assert harness.no_emoji(a_run(replies=["Great news 🚀"])) == "The reply contains an emoji."
    assert harness.no_emoji(a_run(replies=["Plain — text, with café."])) is None


def test_every_agent_has_at_least_one_case():
    from evals.cases import CASES

    assert {case.agent_id for case in CASES} == {"content", "optimizer", "scout", "coach"}
    assert len({case.id for case in CASES}) == len(CASES)
    assert all(case.criteria and case.turns for case in CASES)
