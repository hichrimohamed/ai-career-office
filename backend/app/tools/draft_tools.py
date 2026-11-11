"""Tools for workers that write LinkedIn posts: save ideas and drafts to the Drafts board."""

from claude_agent_sdk import SdkMcpTool, tool

from app.core import drafts, store
from app.tools.project_tools import fail, ok, schema

PILLARS = ", ".join(store.PILLARS)
FORMATS = ", ".join(store.FORMATS)


def build_draft_tools(agent_id: str) -> list[SdkMcpTool]:
    @tool(
        "save_ideas",
        "Save post ideas to the Ideas column of the Drafts board. Each idea: title, hook (first line), "
        f"angle, why (how it helps the AI-engineer job search), pillar ({PILLARS}), proof_missing (optional).",
        {
            "type": "object",
            "properties": {
                "ideas": {
                    "type": "array",
                    "items": schema(
                        {"title": "string", "hook": "string", "angle": "string", "why": "string", "pillar": "string"},
                        {"proof_missing": "string"},
                    ),
                }
            },
            "required": ["ideas"],
        },
    )
    async def save_ideas(args: dict) -> dict:
        try:
            cleaned = [drafts.clean_idea(idea) for idea in args.get("ideas") or []]
        except drafts.DraftError as error:
            return fail(error)
        if not cleaned:
            return fail(drafts.DraftError("No ideas given."))
        return ok({"saved": [{"id": store.add_idea(i, agent_id)["id"], "title": i["title"]} for i in cleaned]})

    @tool(
        "save_draft",
        "Save a full post draft to the Drafts board so the user can copy it. "
        f"pillar: {PILLARS}. format: {FORMATS}. idea_id: the idea it came from, if any. "
        "body: the exact post text, ready to paste into LinkedIn.",
        schema(
            {"title": "string", "pillar": "string", "format": "string", "body": "string"},
            {"asset_needed": "string", "idea_id": "integer"},
        ),
    )
    async def save_draft(args: dict) -> dict:
        try:
            draft = store.add_draft(drafts.clean_draft(args), agent_id)
        except drafts.DraftError as error:
            return fail(error)
        return ok({"saved": {"id": draft["id"], "title": draft["title"], "chars": len(draft["body"])}})

    @tool(
        "update_draft",
        "Revise an existing draft by id with the full new body, and a short note of what changed. "
        "The previous version is kept.",
        schema({"id": "integer", "body": "string", "change_note": "string"}),
    )
    async def update_draft(args: dict) -> dict:
        try:
            body = drafts.text(args.get("body"), "body")
            note = drafts.text(args.get("change_note"), "change_note")
        except drafts.DraftError as error:
            return fail(error)
        draft = store.revise_draft(int(args["id"]), body, note)
        if draft is None:
            return fail(drafts.DraftError(f"No draft with id {args['id']}."))
        return ok({"updated": {"id": draft["id"], "version": draft["version"], "chars": len(draft["body"])}})

    @tool("list_drafts", "List saved ideas and drafts (with ids) on the Drafts board.", {})
    async def list_drafts(args: dict) -> dict:
        return ok({"ideas": store.list_ideas(), "drafts": store.list_drafts()})

    return [save_ideas, save_draft, update_draft, list_drafts]
