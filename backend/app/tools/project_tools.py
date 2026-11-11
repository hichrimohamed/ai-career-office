"""SDK tool wrappers around app.tools.projects."""

import json
from typing import Any

from claude_agent_sdk import tool

from app.tools import projects


def ok(payload: Any) -> dict:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=1)
    return {"content": [{"type": "text", "text": text}]}


def schema(required: dict[str, str], optional: dict[str, str] | None = None) -> dict:
    """JSON Schema with optional fields (the SDK's short dict form makes every field required)."""
    fields = {**required, **(optional or {})}
    return {
        "type": "object",
        "properties": {name: {"type": kind} for name, kind in fields.items()},
        "required": list(required),
    }


def fail(error: Exception) -> dict:
    return {"content": [{"type": "text", "text": f"Error: {error}"}], "is_error": True}


@tool(
    "list_recent_projects",
    "List the user's software projects, most recently modified first, with last commit and README status.",
    schema({}, {"limit": "integer"}),
)
async def list_recent_projects(args: dict) -> dict:
    return ok(projects.list_recent_projects(int(args.get("limit") or 10)))


@tool(
    "list_project_files",
    "List files in one project (most recently modified first). Secret and dependency files are hidden.",
    {"project": str},
)
async def list_project_files(args: dict) -> dict:
    try:
        return ok(projects.list_project_files(args["project"]))
    except projects.ProjectError as error:
        return fail(error)


@tool(
    "read_project_file",
    "Read a text file from a project, e.g. README.md, notes, docs or source. Keys are redacted.",
    {"project": str, "path": str},
)
async def read_project_file(args: dict) -> dict:
    try:
        return ok(projects.read_project_file(args["project"], args["path"]))
    except projects.ProjectError as error:
        return fail(error)


@tool(
    "project_git_log",
    "Recent git commits for a project (date, hash, message). Default: last 14 days.",
    schema({"project": "string"}, {"days": "integer"}),
)
async def project_git_log(args: dict) -> dict:
    try:
        return ok(projects.project_git_log(args["project"], int(args.get("days") or 14)))
    except projects.ProjectError as error:
        return fail(error)


PROJECT_TOOLS = [list_recent_projects, list_project_files, read_project_file, project_git_log]
