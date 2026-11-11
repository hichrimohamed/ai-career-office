import json

from fastapi.testclient import TestClient

from app.core import llm, store
from app.main import app

client = TestClient(app)

DRAFT = {
    "idea_id": None,
    "title": "Untrusted email",
    "pillar": "lesson",
    "format": "text",
    "body": "My agent reads email. [CONFIRM: is it live?] It saved [ADD REAL NUMBER] hours.",
    "asset_needed": "",
}
JOB = {
    "title": "AI Engineer",
    "company": "Acme AI",
    "url": "https://jobs.example.com/acme",
    "location": "Barcelona",
    "work_mode": "hybrid",
    "posted": "",
    "origin": "search",
    "summary": "",
    "fit_score": 72,
    "matched": [],
    "gaps": [],
    "notes": "",
}


def fake_complete(reply, calls):
    async def _complete(system_prompt, prompt):
        calls.append(json.loads(prompt))
        if isinstance(reply, Exception):
            raise reply
        return reply

    return _complete


def by_agent(body: dict) -> dict:
    return {u["agent_id"]: u for u in body["updates"]}


def test_standup_builds_facts_and_next_steps_from_the_boards(monkeypatch):
    store.add_draft(DRAFT, "content")
    store.save_job(JOB, "scout")
    session = store.start_interview("AI engineer", "junior", 5, "coach")
    store.add_answer(session["id"], {
        "area": "rag", "question": "q", "answer": "a", "score": 6, "feedback": "f", "strong_answer": "s",
    })
    calls: list[dict] = []
    reply = 'Sure: {"content": "Two placeholders left in my draft.", "scout": "Acme looks good."}'
    monkeypatch.setattr(llm, "complete", fake_complete(reply, calls))

    updates = by_agent(client.get("/standup").json())

    assert list(updates) == ["content", "optimizer", "scout", "coach"]
    assert updates["content"]["line"] == "Two placeholders left in my draft."
    assert 'draft "Untrusted email" still has 2 placeholders to fill' in updates["content"]["facts"]
    assert updates["content"]["next"]["label"] == 'Finish "Untrusted email"'
    assert 'draft #1 "Untrusted email"' in updates["content"]["next"]["prompt"]
    assert updates["scout"]["next"]["label"] == "Apply to Acme AI"
    assert "mock interview #1 paused at 1/5 questions" in updates["coach"]["facts"]
    assert updates["coach"]["next"]["label"] == "Resume the mock interview"
    # Workers the model skipped fall back to their plain facts.
    assert updates["optimizer"]["line"].startswith("0 rewrites waiting")
    # The model only sees the facts.
    assert calls[0]["content"]["facts"] == updates["content"]["facts"]


def test_standup_is_cached_per_day_and_refresh_reruns_it(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(llm, "complete", fake_complete("{}", calls))

    first = client.get("/standup").json()
    assert client.get("/standup").json() == first
    assert len(calls) == 1

    client.post("/standup")
    assert len(calls) == 2


def test_standup_works_when_the_model_fails(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete(RuntimeError("plan limit"), []))

    updates = by_agent(client.get("/standup").json())

    assert updates["coach"]["line"] == "No mock interview yet; 0 open skill gaps (0 high)."
    assert updates["coach"]["next"]["label"] == "Mock interview"
    assert updates["content"]["next"]["label"] == "Weekly brief"
    assert updates["scout"]["next"]["label"] == "Find AI jobs"


def test_overlong_lines_are_replaced_by_the_facts(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete(json.dumps({"coach": "x" * 500}), []))

    assert by_agent(client.get("/standup").json())["coach"]["line"].startswith("No mock interview yet")


def test_long_titles_are_shortened_on_buttons(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete("{}", []))
    store.add_draft({**DRAFT, "title": "Every email my agent reads is untrusted input"}, "content")

    label = by_agent(client.get("/standup").json())["content"]["next"]["label"]

    assert label == 'Finish "Every email my agent reads is…"'
