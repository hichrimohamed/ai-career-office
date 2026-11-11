"""Tools for the Career Coach: mock interviews, skill gaps and portfolio project suggestions."""

from claude_agent_sdk import SdkMcpTool, tool

from app.core import coaching, store
from app.tools.project_tools import fail, ok

STRING_LIST = {"type": "array", "items": {"type": "string"}}


def build_coach_tools(agent_id: str) -> list[SdkMcpTool]:
    @tool(
        "start_mock_interview",
        "Start a mock interview session before asking the first question. Returns its id. "
        "topic: what it covers. level: e.g. junior, junior-mid, mid. planned_questions: 1-15 (default 5).",
        {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "level": {"type": "string"},
                "planned_questions": {"type": "integer"},
            },
            "required": ["topic"],
        },
    )
    async def start_mock_interview(args: dict) -> dict:
        try:
            data = coaching.clean_start(args)
        except (coaching.CoachingError, ValueError) as error:
            return fail(error)
        session = store.start_interview(data["topic"], data["level"], data["planned_questions"], agent_id)
        return ok({"session_id": session["id"], "planned_questions": session["planned_questions"]})

    @tool(
        "record_answer",
        "Record one scored answer in a mock interview, right after the user answers. "
        f"area: {', '.join(store.INTERVIEW_AREAS)}. answer: the user's answer as he gave it. score: 0-10. "
        "feedback: what was right and what was missing. strong_answer: the key points a strong answer covers.",
        {
            "type": "object",
            "properties": {
                "session_id": {"type": "integer"},
                "area": {"type": "string"},
                "question": {"type": "string"},
                "answer": {"type": "string"},
                "score": {"type": "integer"},
                "feedback": {"type": "string"},
                "strong_answer": {"type": "string"},
            },
            "required": ["session_id", "area", "question", "answer", "score", "feedback"],
        },
    )
    async def record_answer(args: dict) -> dict:
        session = store.get_interview(int(args.get("session_id", 0)))
        if session is None:
            return fail(coaching.CoachingError(f"No interview session {args.get('session_id')}."))
        if session["status"] == "finished":
            return fail(coaching.CoachingError("That session is finished. Start a new one."))
        try:
            answer = coaching.clean_answer(args)
        except (coaching.CoachingError, ValueError) as error:
            return fail(error)
        session = store.add_answer(session["id"], answer)
        return ok({"recorded": len(session["answers"]), "of": session["planned_questions"],
                   "average_score": session["average_score"]})

    @tool(
        "finish_mock_interview",
        "Close a mock interview with a short summary: overall level, strongest and weakest areas, what to do next.",
        {"session_id": int, "summary": str},
    )
    async def finish_mock_interview(args: dict) -> dict:
        session = store.get_interview(int(args.get("session_id", 0)))
        if session is None:
            return fail(coaching.CoachingError(f"No interview session {args.get('session_id')}."))
        try:
            summary = coaching.clean_summary(args.get("summary"))
        except coaching.CoachingError as error:
            return fail(error)
        session = store.finish_interview(session["id"], summary)
        return ok({"finished": session["id"], "answers": len(session["answers"]),
                   "average_score": session["average_score"]})

    @tool(
        "save_skill_gap",
        "Save or update a skill gap (same skill name updates it). "
        f"severity: {', '.join(store.GAP_SEVERITIES)} (high = blocks applications for his target roles). "
        "evidence: where it showed up (interview score, job requirements, missing from profile). "
        "next_step: the smallest concrete action to start closing it.",
        {
            "type": "object",
            "properties": {
                "skill": {"type": "string"},
                "severity": {"type": "string"},
                "evidence": {"type": "string"},
                "next_step": {"type": "string"},
            },
            "required": ["skill", "severity", "evidence"],
        },
    )
    async def save_skill_gap(args: dict) -> dict:
        try:
            gap = store.save_gap(coaching.clean_gap(args), agent_id)
        except coaching.CoachingError as error:
            return fail(error)
        return ok({"saved": {"id": gap["id"], "skill": gap["skill"], "severity": gap["severity"],
                             "status": gap["status"]}})

    @tool(
        "suggest_project",
        "Save a portfolio project that closes one or more skill gaps. pitch: what it is and why a hiring "
        "manager would care. closes_gaps: skill names. stack: technologies. steps: a concrete build plan. "
        "effort: e.g. '1 weekend', '2 weeks of evenings'.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "pitch": {"type": "string"},
                "closes_gaps": STRING_LIST,
                "stack": STRING_LIST,
                "steps": STRING_LIST,
                "effort": {"type": "string"},
            },
            "required": ["title", "pitch", "closes_gaps", "steps"],
        },
    )
    async def suggest_project(args: dict) -> dict:
        try:
            project = store.add_portfolio_project(coaching.clean_project(args), agent_id)
        except coaching.CoachingError as error:
            return fail(error)
        return ok({"saved": {"id": project["id"], "title": project["title"]}})

    @tool(
        "list_coaching",
        "List past mock interviews (scores), skill gaps, suggested projects, and the gaps Maya found in saved jobs.",
        {},
    )
    async def list_coaching(args: dict) -> dict:
        job_gaps = [
            {"job": f"{j['title']} at {j['company']}", "fit_score": j["fit_score"], "gaps": j["gaps"]}
            for j in store.list_jobs()
            if j["gaps"]
        ]
        interviews = [
            {k: s[k] for k in ("id", "topic", "level", "status", "average_score", "summary")}
            | {"answers": [{k: a[k] for k in ("area", "question", "score")} for a in s["answers"]]}
            for s in store.list_interviews()
        ]
        return ok({"interviews": interviews, "skill_gaps": store.list_gaps(),
                   "projects": store.list_portfolio_projects(), "gaps_from_saved_jobs": job_gaps})

    return [start_mock_interview, record_answer, finish_mock_interview, save_skill_gap, suggest_project, list_coaching]
