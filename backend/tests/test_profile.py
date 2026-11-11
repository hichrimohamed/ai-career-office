import asyncio
import json

from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.core import llm, store
from app.main import app
from app.tools.profile_tools import build_profile_tools

client = TestClient(app)


def run_tool(name: str, args: dict) -> dict:
    tool = next(t for t in build_profile_tools("content") if t.name == name)
    return asyncio.run(tool.handler(args))


def test_new_profile_reports_all_core_gaps():
    body = client.get("/profile").json()
    assert body["facts"] == []
    assert body["gaps"] == store.CORE_CATEGORIES


def test_crud_through_api():
    created = client.post("/profile", json={"category": "Location", "fact": "  Barcelona,  or remote "}).json()
    assert (created["category"], created["fact"], created["source"]) == ("location", "Barcelona, or remote", "user")

    updated = client.patch(f"/profile/{created['id']}", json={"fact": "Barcelona or remote in the EU"}).json()
    assert updated["fact"] == "Barcelona or remote in the EU"
    assert "location" not in client.get("/profile").json()["gaps"]

    assert client.delete(f"/profile/{created['id']}").status_code == 204
    assert client.get("/profile").json()["facts"] == []


def test_rejects_bad_category_and_secrets():
    assert client.post("/profile", json={"category": "mood", "fact": "happy"}).status_code == 422
    secret = client.post("/profile", json={"category": "skills", "fact": "my key sk-ant-abcdefghijklmnop1234"})
    assert secret.status_code == 422


def test_agent_tool_saves_with_source_and_updates():
    saved = json.loads(run_tool("save_profile_fact", {"category": "skills", "fact": "RAG with pgvector"})["content"][0]["text"])
    assert saved["saved"]["source"] == "content"

    run_tool("update_profile_fact", {"id": saved["saved"]["id"], "fact": "RAG with pgvector and rerankers"})
    assert [f["fact"] for f in store.list_facts()] == ["RAG with pgvector and rerankers"]


def test_tool_errors_are_reported_not_raised():
    result = run_tool("update_profile_fact", {"id": 999, "fact": "x"})
    assert result["is_error"] is True


def test_profile_and_gaps_are_in_every_agent_prompt():
    store.add_fact("location", "Barcelona", "user")
    prompt = llm.build_system_prompt(AGENTS["content"])
    assert "(location) Barcelona" in prompt
    assert "### Gaps: background, skills, projects, goals, voice" in prompt


def test_every_agent_gets_profile_tools():
    allowed = llm.build_options(AGENTS["content"], None).allowed_tools
    assert "mcp__office__save_profile_fact" in allowed
    assert "mcp__office__list_recent_projects" in allowed
