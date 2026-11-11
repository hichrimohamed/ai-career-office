import asyncio
import json

from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.core import llm, store
from app.main import app
from app.tools.linkedin_tools import build_linkedin_tools

client = TestClient(app)

HEADLINE = {
    "section": "Headline",
    "original": "Mobile Developer | Flutter",
    "rewrite": "AI Engineer | LLM agents & automation (Claude API, Ollama, n8n) | Ex-mobile (Flutter, Swift, Kotlin)",
    "rationale": "Leads with the target role and real stack.",
    "keywords": ["AI Engineer", "LLM", " "],
    "sources": ["original", "fact #6"],
}


def save(args: dict) -> dict:
    tool = next(t for t in build_linkedin_tools("optimizer") if t.name == "save_section_rewrite")
    result = asyncio.run(tool.handler(args))
    return {**result, "data": None if result.get("is_error") else json.loads(result["content"][0]["text"])}


def test_saves_rewrite_next_to_original():
    saved = save(HEADLINE)["data"]["saved"]
    section = client.get("/linkedin").json()["sections"][0]
    assert section["id"] == saved["id"]
    assert (section["section"], section["original"], section["status"]) == ("headline", "Mobile Developer | Flutter", "proposed")
    assert section["keywords"] == ["AI Engineer", "LLM"]
    assert section["sources"] == ["original", "fact #6"]


def test_resaving_same_section_keeps_previous_and_original():
    save(HEADLINE)
    client.patch(f"/linkedin/{store.list_sections()[0]['id']}", json={"status": "applied"})

    second = save({**HEADLINE, "original": "", "rewrite": "AI Engineer | Agents & automation"})["data"]["saved"]

    section = store.get_section(second["id"])
    assert section["version"] == 2
    assert section["previous_rewrite"] == HEADLINE["rewrite"]
    assert section["original"] == "Mobile Developer | Flutter"  # kept when not re-pasted
    assert section["status"] == "proposed"  # a new rewrite needs applying again
    assert len(store.list_sections()) == 1


def test_rejects_unsourced_too_long_and_unlabeled():
    assert save({**HEADLINE, "sources": []})["is_error"]
    assert save({**HEADLINE, "rewrite": "x" * 221})["is_error"]
    assert save({**HEADLINE, "section": "experience"})["is_error"]  # needs a label
    assert save({**HEADLINE, "section": "hobbies"})["is_error"]
    assert save({**HEADLINE, "rewrite": "AI Engineer sk-ant-abcdefghijklmnop1234"})["is_error"]
    assert store.list_sections() == []


def test_sections_are_ordered_like_a_profile():
    save({**HEADLINE, "section": "experience", "label": "Software Engineer, Thales", "rewrite": "Built HMI."})
    save({**HEADLINE, "section": "about", "rewrite": "I build agents."})
    save(HEADLINE)
    assert [s["section"] for s in store.list_sections()] == ["headline", "about", "experience"]


def test_board_api_edit_status_delete():
    section_id = save(HEADLINE)["data"]["saved"]["id"]
    assert client.patch(f"/linkedin/{section_id}", json={"rewrite": "x" * 221}).status_code == 422
    assert client.patch(f"/linkedin/{section_id}", json={"status": "live"}).status_code == 422
    edited = client.patch(f"/linkedin/{section_id}", json={"rewrite": "AI Engineer", "status": "applied"}).json()
    assert (edited["rewrite"], edited["version"], edited["status"]) == ("AI Engineer", 2, "applied")
    assert client.delete(f"/linkedin/{section_id}").status_code == 204
    assert client.get("/linkedin").json()["sections"] == []


def test_leo_is_registered_with_his_tools_and_actions():
    agents = {a["id"]: a for a in client.get("/agents").json()}
    assert agents["optimizer"]["name"] == "Leo"
    assert "Optimize my profile" in [q["label"] for q in agents["optimizer"]["quick_actions"]]
    assert "Weekly brief" in [q["label"] for q in agents["content"]["quick_actions"]]

    allowed = set(llm.build_options(AGENTS["optimizer"], None).allowed_tools)
    assert {"mcp__office__save_section_rewrite", "mcp__office__save_profile_fact", "WebSearch"} <= allowed
    assert "mcp__office__save_draft" not in allowed
