import asyncio
import json

from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.core import llm, store
from app.main import app
from app.tools.draft_tools import build_draft_tools

client = TestClient(app)

IDEA = {
    "title": "Cost per clip",
    "hook": "My clipping agent cost [ADD REAL NUMBER] per video. Now it costs less.",
    "angle": "Hybrid Ollama plus Claude API",
    "why": "Shows cost control, which AI teams hire for",
    "pillar": "Engineering-Decision",
}
DRAFT = {"title": "Cost per clip", "pillar": "engineering-decision", "format": "text", "body": "Line one.\n\nLine two."}


def run_tool(name: str, args: dict) -> dict:
    tool = next(t for t in build_draft_tools("content") if t.name == name)
    result = asyncio.run(tool.handler(args))
    return {**result, "data": json.loads(result["content"][0]["text"]) if not result.get("is_error") else None}


def test_save_ideas_then_draft_marks_idea_drafted():
    saved = run_tool("save_ideas", {"ideas": [IDEA]})["data"]["saved"]
    idea_id = saved[0]["id"]
    assert store.get_idea(idea_id)["pillar"] == "engineering-decision"

    draft = run_tool("save_draft", {**DRAFT, "idea_id": idea_id})["data"]["saved"]

    board = client.get("/drafts").json()
    assert board["ideas"][0]["status"] == "drafted"
    assert board["drafts"][0]["id"] == draft["id"]
    assert board["drafts"][0]["body"] == "Line one.\n\nLine two."
    assert board["drafts"][0]["source"] == "content"


def test_invalid_pillar_format_and_secrets_are_rejected():
    assert run_tool("save_ideas", {"ideas": [{**IDEA, "pillar": "memes"}]})["is_error"]
    assert run_tool("save_draft", {**DRAFT, "format": "tiktok"})["is_error"]
    assert run_tool("save_draft", {**DRAFT, "body": "token = sk-ant-abcdefghijklmnop1234"})["is_error"]
    assert run_tool("save_draft", {**DRAFT, "body": "x" * 3001})["is_error"]
    assert run_tool("save_draft", {**DRAFT, "idea_id": 404})["is_error"]
    assert client.get("/drafts").json() == {"ideas": [], "drafts": []}


def test_revisions_bump_version_and_keep_history():
    draft_id = run_tool("save_draft", DRAFT)["data"]["saved"]["id"]

    updated = run_tool("update_draft", {"id": draft_id, "body": "Shorter.", "change_note": "Cut the intro"})
    assert updated["data"]["updated"]["version"] == 2

    edited = client.patch(f"/drafts/{draft_id}", json={"body": "Shorter still.", "status": "ready"}).json()
    assert (edited["version"], edited["status"], edited["change_note"]) == (3, "ready", "Edited by you")
    with store.connect() as conn:
        history = [r["body"] for r in conn.execute("SELECT body FROM draft_revisions ORDER BY version")]
    assert history == ["Line one.\n\nLine two.", "Shorter."]


def test_unchanged_body_does_not_create_a_version():
    draft_id = run_tool("save_draft", DRAFT)["data"]["saved"]["id"]
    assert client.patch(f"/drafts/{draft_id}", json={"body": DRAFT["body"]}).json()["version"] == 1


def test_board_api_status_and_delete():
    idea_id = run_tool("save_ideas", {"ideas": [IDEA]})["data"]["saved"][0]["id"]
    draft_id = run_tool("save_draft", DRAFT)["data"]["saved"]["id"]

    assert client.patch(f"/drafts/{draft_id}", json={"status": "published"}).status_code == 422
    assert client.patch(f"/ideas/{idea_id}", json={"status": "dismissed"}).json()["status"] == "dismissed"
    assert client.delete(f"/drafts/{draft_id}").status_code == 204
    assert client.get("/drafts").json() == {"ideas": [], "drafts": []}
    assert client.delete(f"/drafts/{draft_id}").status_code == 404


def test_nora_has_draft_tools_and_board_instructions():
    options = llm.build_options(AGENTS["content"], None)
    assert {"mcp__office__save_draft", "mcp__office__save_ideas", "mcp__office__update_draft"} <= set(options.allowed_tools)
    assert "Drafts board" in AGENTS["content"].system_prompt
