import json
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

load_dotenv()

from app.agents import AGENTS, Agent  # noqa: E402
from app.core import coaching, drafts, jobs, linkedin, llm, profile, sessions, standup, store  # noqa: E402

app = FastAPI(title="AI Career Office")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class FactCreate(BaseModel):
    category: str
    fact: str


class FactUpdate(BaseModel):
    category: str | None = None
    fact: str | None = None


class DraftUpdate(BaseModel):
    body: str | None = None
    status: str | None = None


class IdeaUpdate(BaseModel):
    status: str


class JobUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


class OutreachUpdate(BaseModel):
    message: str | None = None
    status: str | None = None


class StatusUpdate(BaseModel):
    status: str


class SectionUpdate(BaseModel):
    rewrite: str | None = None
    status: str | None = None


def get_agent(agent_id: str) -> Agent:
    agent = AGENTS.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{agent_id}'")
    return agent


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/agents")
def list_agents() -> list[dict]:
    return [
        {"id": a.id, "name": a.name, "role": a.role, "quick_actions": a.quick_actions} for a in AGENTS.values()
    ]


@app.get("/agents/{agent_id}/messages")
def get_messages(agent_id: str) -> list[dict]:
    return store.list_messages(get_agent(agent_id).id)


@app.get("/profile")
def get_profile() -> dict:
    facts = store.list_facts()
    return {"facts": facts, "gaps": store.profile_gaps(facts), "categories": store.PROFILE_CATEGORIES}


@app.post("/profile", status_code=201)
def create_fact(body: FactCreate) -> dict:
    try:
        category, fact = profile.clean(body.category, body.fact)
    except profile.ProfileError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.add_fact(category, fact, source="user")


@app.patch("/profile/{fact_id}")
def edit_fact(fact_id: int, body: FactUpdate) -> dict:
    existing = store.get_fact(fact_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    try:
        category, fact = profile.clean(body.category or existing["category"], body.fact or existing["fact"])
    except profile.ProfileError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.update_fact(fact_id, fact, category)


@app.delete("/profile/{fact_id}", status_code=204)
def remove_fact(fact_id: int) -> None:
    if not store.delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fact not found")


@app.get("/drafts")
def get_drafts() -> dict:
    return {"ideas": store.list_ideas(), "drafts": store.list_drafts()}


@app.patch("/drafts/{draft_id}")
def edit_draft(draft_id: int, body: DraftUpdate) -> dict:
    if store.get_draft(draft_id) is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    try:
        if body.body is not None:
            store.revise_draft(draft_id, drafts.text(body.body, "body"), "Edited by you")
        if body.status is not None:
            store.set_draft_status(draft_id, drafts.choice(body.status, store.DRAFT_STATUSES, "status"))
    except drafts.DraftError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.get_draft(draft_id)


@app.delete("/drafts/{draft_id}", status_code=204)
def remove_draft(draft_id: int) -> None:
    if not store.delete_draft(draft_id):
        raise HTTPException(status_code=404, detail="Draft not found")


@app.patch("/ideas/{idea_id}")
def edit_idea(idea_id: int, body: IdeaUpdate) -> dict:
    if store.get_idea(idea_id) is None:
        raise HTTPException(status_code=404, detail="Idea not found")
    try:
        status = drafts.choice(body.status, store.IDEA_STATUSES, "status")
    except drafts.DraftError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.set_idea_status(idea_id, status)


@app.get("/linkedin")
def get_linkedin() -> dict:
    return {"sections": store.list_sections(), "limits": store.LINKEDIN_SECTIONS}


@app.patch("/linkedin/{section_id}")
def edit_section(section_id: int, body: SectionUpdate) -> dict:
    current = store.get_section(section_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Section not found")
    try:
        rewrite = None
        if body.rewrite is not None:
            limit = store.LINKEDIN_SECTIONS[current["section"]]
            rewrite = linkedin.check_text(body.rewrite, "rewrite", limit)
        status = None
        if body.status is not None:
            status = drafts.choice(body.status, store.SECTION_STATUSES, "status")
    except (linkedin.SectionError, drafts.DraftError) as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.update_section(section_id, rewrite, status)


@app.delete("/linkedin/{section_id}", status_code=204)
def remove_section(section_id: int) -> None:
    if not store.delete_section(section_id):
        raise HTTPException(status_code=404, detail="Section not found")


@app.get("/jobs")
def get_jobs() -> dict:
    return {"jobs": store.list_jobs(), "outreach": store.list_outreach(), "statuses": store.JOB_STATUSES}


@app.patch("/jobs/{job_id}")
def edit_job(job_id: int, body: JobUpdate) -> dict:
    if store.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        status = jobs.choice_of(body.status, store.JOB_STATUSES, "status") if body.status is not None else None
        notes = jobs.text(body.notes, "notes", 1000) if body.notes is not None else None
    except jobs.JobError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.update_job(job_id, status, notes)


@app.delete("/jobs/{job_id}", status_code=204)
def remove_job(job_id: int) -> None:
    if not store.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")


@app.patch("/outreach/{outreach_id}")
def edit_outreach(outreach_id: int, body: OutreachUpdate) -> dict:
    if store.get_outreach(outreach_id) is None:
        raise HTTPException(status_code=404, detail="Outreach note not found")
    try:
        message = (
            jobs.text(body.message, "message", store.OUTREACH_MAX_CHARS, required=True)
            if body.message is not None
            else None
        )
        status = jobs.choice_of(body.status, store.OUTREACH_STATUSES, "status") if body.status is not None else None
    except jobs.JobError as error:
        raise HTTPException(status_code=422, detail=str(error))
    return store.update_outreach(outreach_id, message, status)


@app.delete("/outreach/{outreach_id}", status_code=204)
def remove_outreach(outreach_id: int) -> None:
    if not store.delete_outreach(outreach_id):
        raise HTTPException(status_code=404, detail="Outreach note not found")


@app.get("/coaching")
def get_coaching() -> dict:
    return {
        "interviews": store.list_interviews(),
        "gaps": store.list_gaps(),
        "projects": store.list_portfolio_projects(),
        "gap_statuses": store.GAP_STATUSES,
        "project_statuses": store.PROJECT_STATUSES,
    }


def _status(value: str, options: list[str]) -> str:
    try:
        return coaching.choice(value, options, "status")
    except coaching.CoachingError as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.patch("/gaps/{gap_id}")
def edit_gap(gap_id: int, body: StatusUpdate) -> dict:
    if store.get_gap(gap_id) is None:
        raise HTTPException(status_code=404, detail="Gap not found")
    return store.update_gap(gap_id, _status(body.status, store.GAP_STATUSES))


@app.delete("/gaps/{gap_id}", status_code=204)
def remove_gap(gap_id: int) -> None:
    if not store.delete_gap(gap_id):
        raise HTTPException(status_code=404, detail="Gap not found")


@app.patch("/portfolio/{project_id}")
def edit_portfolio_project(project_id: int, body: StatusUpdate) -> dict:
    if store.get_portfolio_project(project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return store.update_portfolio_project(project_id, _status(body.status, store.PROJECT_STATUSES))


@app.delete("/portfolio/{project_id}", status_code=204)
def remove_portfolio_project(project_id: int) -> None:
    if not store.delete_portfolio_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@app.delete("/interviews/{session_id}", status_code=204)
def remove_interview(session_id: int) -> None:
    if not store.delete_interview(session_id):
        raise HTTPException(status_code=404, detail="Interview not found")


@app.get("/standup")
async def get_standup() -> dict:
    """Today's standup; runs it on the first call of the day."""
    return await standup.todays_standup()


@app.post("/standup")
async def rerun_standup() -> dict:
    return await standup.todays_standup(refresh=True)


@app.get("/usage")
def get_usage(days: int = 14) -> list[dict]:
    """Tokens and cost per day, agent and model, to see where the plan's credit goes."""
    return store.usage_by_day(days)


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/agents/{agent_id}/chat")
async def chat(agent_id: str, request: ChatRequest) -> StreamingResponse:
    agent = get_agent(agent_id)
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message is empty")

    turn = sessions.plan_turn(agent, message)
    store.add_message(agent.id, "user", message)

    async def events() -> AsyncIterator[str]:
        reply: list[str] = []
        session_cost = turn.spent_usd
        try:
            async for event in llm.stream_agent(agent, turn.prompt, turn.resume, turn.tier, turn.spent_usd):
                if event["type"] == "usage":
                    store.add_usage(agent.id, event["model"], event["usage"])
                    session_cost = event["usage"]["session_cost_usd"]
                    continue
                if event["type"] == "text":
                    reply.append(event["text"])
                elif event["type"] == "done":
                    store.set_session(
                        agent.id, event["session_id"], turn.day, turn.tier, turn.context_hash, session_cost
                    )
                yield sse(event)
        except Exception as exc:  # surface SDK/CLI failures to the chat panel
            yield sse({"type": "error", "message": str(exc)})
        finally:
            if reply:
                store.add_message(agent.id, "assistant", "".join(reply))

    return StreamingResponse(events(), media_type="text/event-stream")
