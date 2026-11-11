"""Tools for the Job & People Scout: save jobs, fit analyses and outreach notes to the Jobs board."""

from claude_agent_sdk import SdkMcpTool, tool

from app.core import jobs, store
from app.tools.project_tools import fail, ok

STRING_LIST = {"type": "array", "items": {"type": "string"}}


def build_job_tools(agent_id: str) -> list[SdkMcpTool]:
    @tool(
        "save_job",
        "Save a job posting to the Jobs board, or update it if already saved (same url, or same company+title). "
        "origin: 'search' (needs the url you found it at) or 'pasted' (the user pasted the description). "
        f"work_mode: {', '.join(store.WORK_MODES)}. posted: date as shown, or 'unknown'. "
        "fit_score: 0-100, honest. matched: requirements he meets, each with its evidence. "
        "gaps: requirements he doesn't meet yet.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "company": {"type": "string"},
                "url": {"type": "string"},
                "location": {"type": "string"},
                "work_mode": {"type": "string"},
                "posted": {"type": "string"},
                "origin": {"type": "string"},
                "summary": {"type": "string"},
                "fit_score": {"type": "integer"},
                "matched": STRING_LIST,
                "gaps": STRING_LIST,
                "notes": {"type": "string"},
            },
            "required": ["title", "company", "origin", "summary"],
        },
    )
    async def save_job(args: dict) -> dict:
        try:
            job = store.save_job(jobs.clean_job(args), agent_id)
        except (jobs.JobError, ValueError) as error:
            return fail(error)
        return ok({"saved": {"id": job["id"], "title": job["title"], "company": job["company"],
                             "fit_score": job["fit_score"]}})

    @tool(
        "save_outreach",
        f"Save an outreach note (max {store.OUTREACH_MAX_CHARS} characters, LinkedIn's connection-note limit). "
        "target: the kind of person, e.g. 'Engineering manager, AI team at <company>'. Don't name private "
        "individuals. how_to_find: a LinkedIn search the user can run himself. job_id: the related job, if any.",
        {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "how_to_find": {"type": "string"},
                "message": {"type": "string"},
                "job_id": {"type": "integer"},
            },
            "required": ["target", "message"],
        },
    )
    async def save_outreach(args: dict) -> dict:
        try:
            item = store.add_outreach(jobs.clean_outreach(args), agent_id)
        except (jobs.JobError, ValueError) as error:
            return fail(error)
        return ok({"saved": {"id": item["id"], "chars": len(item["message"])}})

    @tool("list_jobs", "List the jobs and outreach notes on the Jobs board, with ids and statuses.", {})
    async def list_jobs(args: dict) -> dict:
        return ok({"jobs": store.list_jobs(), "outreach": store.list_outreach()})

    return [save_job, save_outreach, list_jobs]
