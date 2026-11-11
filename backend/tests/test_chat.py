import json

from claude_agent_sdk import ResultMessage, StreamEvent
from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.agents.base import INTERVIEW_ACTION
from app.core import llm, store
from app.main import app

client = TestClient(app)


def text_delta(text: str) -> StreamEvent:
    return StreamEvent(
        uuid="u",
        session_id="sess-1",
        event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
    )


def result(session_id: str = "sess-1", is_error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id=session_id,
        result="boom" if is_error else "ok",
    )


def fake_query(messages, calls):
    async def _query(prompt, options):
        calls.append({"prompt": prompt, "resume": options.resume, "model": options.model})
        for message in messages:
            yield message

    return _query


def parse_sse(body: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in body.splitlines() if line.startswith("data: ")]


def test_lists_content_agent():
    agents = [{k: a[k] for k in ("id", "name", "role")} for a in client.get("/agents").json()]
    assert {"id": "content", "name": "Nora", "role": "Content Strategist"} in agents


def test_chat_streams_and_persists(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("Idea 1: "), text_delta("RAG evals"), result()], calls))

    response = client.post("/agents/content/chat", json={"message": "3 post ideas about RAG"})

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [e["type"] for e in events] == ["text", "text", "done"]
    assert calls[0]["resume"] is None
    assert calls[0]["prompt"].startswith("<office_context>")
    assert calls[0]["prompt"].endswith("3 post ideas about RAG")
    saved = [(m["role"], m["content"]) for m in client.get("/agents/content/messages").json()]
    assert saved == [("user", "3 post ideas about RAG"), ("assistant", "Idea 1: RAG evals")]


def test_second_message_resumes_session(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-42")], calls))

    client.post("/agents/content/chat", json={"message": "first"})
    client.post("/agents/content/chat", json={"message": "second"})

    assert [c["resume"] for c in calls] == [None, "sess-42"]
    # The profile hasn't changed, so the second message travels without the context block.
    assert calls[1]["prompt"] == "second"


def test_changed_profile_is_resent_to_a_running_session(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-42")], calls))

    client.post("/agents/content/chat", json={"message": "first"})
    client.post("/profile", json={"category": "location", "fact": "Barcelona"})
    client.post("/agents/content/chat", json={"message": "second"})

    assert calls[1]["resume"] == "sess-42"
    assert "(location) Barcelona" in calls[1]["prompt"]


def test_heavy_quick_action_starts_a_new_session(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-42")], calls))

    client.post("/agents/content/chat", json={"message": "first"})
    client.post("/agents/content/chat", json={"message": "Write this week's brief."})

    assert calls[1]["resume"] is None
    assert "Earlier in this chat" not in calls[1]["prompt"]


def test_yesterdays_session_is_not_resumed(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-42")], calls))

    client.post("/agents/content/chat", json={"message": "first"})
    saved = store.get_session("content")
    store.set_session("content", saved["session_id"], "2000-01-01", saved["model"], saved["context_hash"])
    client.post("/agents/content/chat", json={"message": "second"})

    assert calls[1]["resume"] is None
    assert "Earlier in this chat" in calls[1]["prompt"]
    assert "User: first" in calls[1]["prompt"]


def test_profile_interview_runs_on_the_fast_model(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-7")], calls))
    monkeypatch.setenv("MODEL_DEFAULT", "sonnet")
    monkeypatch.setenv("MODEL_FAST", "haiku")

    client.post("/agents/content/chat", json={"message": "first"})
    client.post("/agents/content/chat", json={"message": INTERVIEW_ACTION["prompt"]})
    client.post("/agents/content/chat", json={"message": "I live in Barcelona"})

    assert [c["model"] for c in calls] == ["sonnet", "haiku", "haiku"]
    assert [c["resume"] for c in calls] == [None, None, "sess-7"]


def test_agents_never_load_account_connectors():
    options = llm.build_options(AGENTS["content"], None)
    assert options.strict_mcp_config is True
    assert options.env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "false"
    assert list(options.mcp_servers) == ["office"]


def test_usage_is_recorded_and_hidden_from_the_ui(monkeypatch):
    metered = result()
    metered.usage = {"input_tokens": 10, "cache_creation_input_tokens": 200, "cache_read_input_tokens": 3000, "output_tokens": 40}
    metered.total_cost_usd = 0.0123
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), metered], []))

    events = parse_sse(client.post("/agents/content/chat", json={"message": "hi"}).text)

    assert [e["type"] for e in events] == ["text", "done"]
    row = client.get("/usage").json()[0]
    assert (row["agent_id"], row["cache_read_tokens"], row["output_tokens"], row["cost_usd"]) == ("content", 3000, 40, 0.0123)

    # The SDK reports a running total for a resumed session: only the increase is this message's cost.
    metered.total_cost_usd = 0.02
    client.post("/agents/content/chat", json={"message": "again"})
    assert client.get("/usage").json()[0]["cost_usd"] == 0.02
    assert llm.build_options(AGENTS["content"], "sess-1", spent_usd=0.02).max_budget_usd == 1.02


def test_error_result_is_streamed(monkeypatch):
    monkeypatch.setattr(llm, "query", fake_query([result(is_error=True)], []))

    events = parse_sse(client.post("/agents/content/chat", json={"message": "hi"}).text)

    assert events == [{"type": "error", "message": "boom"}]


def test_unknown_agent_is_404():
    assert client.post("/agents/nope/chat", json={"message": "hi"}).status_code == 404


def test_empty_message_is_rejected():
    assert client.post("/agents/content/chat", json={"message": "  "}).status_code == 422


def block_start(block_type: str, **extra) -> StreamEvent:
    return StreamEvent(
        uuid="u",
        session_id="sess-1",
        event={"type": "content_block_start", "content_block": {"type": block_type, **extra}},
    )


def test_tool_calls_are_reported_and_split_paragraphs(monkeypatch):
    stream = [
        block_start("text"),
        text_delta("Scanning."),
        block_start("tool_use", name="mcp__office__list_recent_projects"),
        block_start("text"),
        text_delta("Found 3."),
        result(),
    ]
    monkeypatch.setattr(llm, "query", fake_query(stream, []))

    events = parse_sse(client.post("/agents/content/chat", json={"message": "brief"}).text)

    assert {"type": "tool", "name": "mcp__office__list_recent_projects"} in events
    saved = client.get("/agents/content/messages").json()[-1]["content"]
    assert saved == "Scanning.\n\nFound 3."
