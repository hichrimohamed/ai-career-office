import asyncio
import json

from fastapi.testclient import TestClient

from app.agents import AGENTS
from app.core import llm, store
from app.main import app
from app.tools.job_tools import build_job_tools

client = TestClient(app)

JOB = {
    "title": "AI Engineer",
    "company": "Acme AI",
    "url": "https://jobs.example.com/acme/ai-engineer",
    "location": "Barcelona",
    "work_mode": "Hybrid",
    "posted": "2026-10-12",
    "origin": "search",
    "summary": "LLM agents for customer support.",
    "fit_score": 72,
    "matched": ["LLM agents: clipping agent (fact #7)", ""],
    "gaps": ["Production RAG at scale"],
}


def run(name: str, args: dict) -> dict:
    tool = next(t for t in build_job_tools("scout") if t.name == name)
    result = asyncio.run(tool.handler(args))
    return {**result, "data": None if result.get("is_error") else json.loads(result["content"][0]["text"])}


def test_save_job_and_board_lists_it():
    saved = run("save_job", JOB)["data"]["saved"]
    job = client.get("/jobs").json()["jobs"][0]
    assert job["id"] == saved["id"]
    assert (job["work_mode"], job["fit_score"], job["status"], job["source"]) == ("hybrid", 72, "saved", "scout")
    assert job["matched"] == ["LLM agents: clipping agent (fact #7)"]


def test_same_url_updates_instead_of_duplicating():
    run("save_job", JOB)
    run("save_job", {**JOB, "fit_score": 80, "summary": "Updated."})
    jobs = store.list_jobs()
    assert len(jobs) == 1
    assert (jobs[0]["fit_score"], jobs[0]["summary"]) == (80, "Updated.")


def test_pasted_job_needs_no_url_and_dedupes_by_company_title():
    pasted = {**JOB, "url": "", "origin": "pasted"}
    run("save_job", pasted)
    run("save_job", {**pasted, "company": "ACME AI", "fit_score": None})
    jobs = store.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["fit_score"] == 72  # an analysis without a score keeps the old one


def test_rejects_unverifiable_or_invalid_jobs():
    assert run("save_job", {**JOB, "url": ""})["is_error"]  # searched but no link
    assert run("save_job", {**JOB, "url": "javascript:alert(1)"})["is_error"]
    assert run("save_job", {**JOB, "fit_score": 140})["is_error"]
    assert run("save_job", {**JOB, "work_mode": "moon"})["is_error"]
    assert store.list_jobs() == []


def test_outreach_respects_linkedin_note_limit():
    job_id = run("save_job", JOB)["data"]["saved"]["id"]
    ok = run("save_outreach", {"target": "Engineering manager, AI team at Acme AI", "message": "Hello" * 8,
                               "how_to_find": '"engineering manager" AI Acme', "job_id": job_id})
    assert ok["data"]["saved"]["chars"] == 40
    assert run("save_outreach", {"target": "Recruiter", "message": "x" * 301})["is_error"]
    assert run("save_outreach", {"target": "Recruiter", "message": "hi", "job_id": 999})["is_error"]
    assert client.get("/jobs").json()["outreach"][0]["job_id"] == job_id


def test_board_api_status_archive_and_outreach_edits():
    job_id = run("save_job", JOB)["data"]["saved"]["id"]
    note_id = run("save_outreach", {"target": "Recruiter", "message": "Hello"})["data"]["saved"]["id"]

    assert client.patch(f"/jobs/{job_id}", json={"status": "hired"}).status_code == 422
    assert client.patch(f"/jobs/{job_id}", json={"status": "applied"}).json()["status"] == "applied"
    client.patch(f"/jobs/{job_id}", json={"status": "archived"})
    assert client.get("/jobs").json()["jobs"] == []  # archived jobs leave the board

    assert client.patch(f"/outreach/{note_id}", json={"message": "x" * 301}).status_code == 422
    edited = client.patch(f"/outreach/{note_id}", json={"message": "Hi there", "status": "sent"}).json()
    assert (edited["message"], edited["status"]) == ("Hi there", "sent")
    assert client.delete(f"/outreach/{note_id}").status_code == 204
    assert client.delete(f"/jobs/{job_id}").status_code == 204


def test_jobs_sorted_by_fit():
    run("save_job", {**JOB, "url": "https://a.example/1", "fit_score": 50})
    run("save_job", {**JOB, "url": "https://a.example/2", "fit_score": None})
    run("save_job", {**JOB, "url": "https://a.example/3", "fit_score": 90})
    assert [j["fit_score"] for j in store.list_jobs()] == [90, 50, None]


def test_maya_is_registered_with_web_and_job_tools():
    agents = {a["id"]: a for a in client.get("/agents").json()}
    paste = next(q for q in agents["scout"]["quick_actions"] if q["label"] == "Check a job post")
    assert paste["send"] is False
    allowed = set(llm.build_options(AGENTS["scout"], None).allowed_tools)
    assert {"mcp__office__save_job", "mcp__office__save_outreach", "WebSearch", "WebFetch"} <= allowed
