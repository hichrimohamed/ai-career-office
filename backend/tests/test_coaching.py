import asyncio
import json

from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.core import llm, store
from app.main import app
from app.tools.coach_tools import build_coach_tools

client = TestClient(app)


def run(name: str, args: dict) -> dict:
    tool = next(t for t in build_coach_tools("coach") if t.name == name)
    result = asyncio.run(tool.handler(args))
    return {**result, "data": None if result.get("is_error") else json.loads(result["content"][0]["text"])}


def answer(session_id: int, score: int, area: str = "rag") -> dict:
    return run("record_answer", {
        "session_id": session_id, "area": area, "question": "How would you evaluate a RAG system?",
        "answer": "Golden set and recall@k.", "score": score, "feedback": "Good start, missing faithfulness.",
        "strong_answer": "Retrieval metrics, faithfulness, answer quality, regression set.",
    })


def test_five_question_session_with_scores_and_summary():
    session_id = run("start_mock_interview", {"topic": "AI engineer basics"})["data"]["session_id"]
    for score in [8, 6, 4, 7, 5]:
        answer(session_id, score)
    finished = run("finish_mock_interview", {"session_id": session_id, "summary": "Solid on agents, weak on evals."})

    assert finished["data"] == {"finished": session_id, "answers": 5, "average_score": 6.0}
    interview = client.get("/coaching").json()["interviews"][0]
    assert (interview["status"], interview["level"], len(interview["answers"])) == ("finished", "junior-mid", 5)


def test_answers_are_validated_and_finished_sessions_are_closed():
    session_id = run("start_mock_interview", {"topic": "RAG", "planned_questions": 2})["data"]["session_id"]
    assert answer(session_id, 11)["is_error"]
    assert answer(session_id, 5, area="astrology")["is_error"]
    assert answer(999, 5)["is_error"]
    assert run("start_mock_interview", {"topic": "RAG", "planned_questions": 40})["is_error"]

    run("finish_mock_interview", {"session_id": session_id, "summary": "Stopped early."})
    assert answer(session_id, 5)["is_error"]


def test_gaps_upsert_by_skill_and_reopen():
    first = run("save_skill_gap", {"skill": "Python", "severity": "high", "evidence": "Must-have at Ambit"})
    gap_id = first["data"]["saved"]["id"]
    client.patch(f"/gaps/{gap_id}", json={"status": "closed"})

    again = run("save_skill_gap", {"skill": "python", "severity": "medium", "evidence": "Interview score 4"})

    gaps = client.get("/coaching").json()["gaps"]
    assert len(gaps) == 1
    assert again["data"]["saved"]["id"] == gap_id
    assert (gaps[0]["severity"], gaps[0]["status"]) == ("medium", "open")  # new evidence reopens it


def test_gaps_sorted_by_severity_closed_last():
    for skill, severity in [("Docker", "low"), ("Evals", "medium"), ("Python", "high")]:
        run("save_skill_gap", {"skill": skill, "severity": severity, "evidence": "x"})
    python_id = next(g["id"] for g in store.list_gaps() if g["skill"] == "Python")
    client.patch(f"/gaps/{python_id}", json={"status": "closed"})
    assert [g["skill"] for g in store.list_gaps()] == ["Evals", "Docker", "Python"]


def test_projects_need_steps_and_board_status_changes():
    assert run("suggest_project", {"title": "RAG demo", "pitch": "x", "closes_gaps": ["Python"], "steps": []})["is_error"]
    saved = run("suggest_project", {
        "title": "Python RAG over my READMEs", "pitch": "Shows Python and evals.", "closes_gaps": ["Python", "RAG"],
        "stack": ["Python", "FastAPI"], "steps": ["Ingest", "Embed", "Eval"], "effort": "1 weekend",
    })["data"]["saved"]
    assert client.patch(f"/portfolio/{saved['id']}", json={"status": "done"}).status_code == 422
    assert client.patch(f"/portfolio/{saved['id']}", json={"status": "building"}).json()["status"] == "building"
    project = client.get("/coaching").json()["projects"][0]
    assert project["steps"] == ["Ingest", "Embed", "Eval"]
    assert client.delete(f"/portfolio/{saved['id']}").status_code == 204


def test_list_coaching_includes_gaps_from_saved_jobs():
    store.save_job({
        "title": "Junior AI Engineer", "company": "Ambit", "url": "https://x.example/1", "location": "", "work_mode": "remote",
        "posted": "unknown", "origin": "search", "summary": "", "fit_score": 65, "matched": [], "gaps": ["Python"],
        "notes": "",
    }, "scout")
    data = run("list_coaching", {})["data"]
    assert data["gaps_from_saved_jobs"] == [{"job": "Junior AI Engineer at Ambit", "fit_score": 65, "gaps": ["Python"]}]


def test_kai_is_registered_without_web_access():
    allowed = set(llm.build_options(AGENTS["coach"], None).allowed_tools)
    assert {"mcp__office__start_mock_interview", "mcp__office__record_answer", "mcp__office__save_skill_gap"} <= allowed
    assert "WebSearch" not in allowed
    assert [a["id"] for a in client.get("/agents").json()] == ["content", "optimizer", "scout", "coach"]
