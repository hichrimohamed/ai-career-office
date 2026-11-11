import json

from claude_agent_sdk import ResultMessage, StreamEvent
from fastapi.testclient import TestClient

from app.core import llm
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
        calls.append({"prompt": prompt, "resume": options.resume})
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
    assert calls == [{"prompt": "3 post ideas about RAG", "resume": None}]
    saved = [(m["role"], m["content"]) for m in client.get("/agents/content/messages").json()]
    assert saved == [("user", "3 post ideas about RAG"), ("assistant", "Idea 1: RAG evals")]


def test_second_message_resumes_session(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "query", fake_query([text_delta("hi"), result("sess-42")], calls))

    client.post("/agents/content/chat", json={"message": "first"})
    client.post("/agents/content/chat", json={"message": "second"})

    assert [c["resume"] for c in calls] == [None, "sess-42"]


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
