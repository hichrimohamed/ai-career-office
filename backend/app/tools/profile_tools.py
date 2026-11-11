"""Profile tools every agent gets. `source` records which worker saved a fact."""

from claude_agent_sdk import SdkMcpTool, tool

from app.core import profile, store
from app.tools.project_tools import fail, ok, schema

CATEGORY_HELP = ", ".join(store.PROFILE_CATEGORIES)


def build_profile_tools(agent_id: str) -> list[SdkMcpTool]:
    @tool(
        "save_profile_fact",
        f"Save one durable fact about the user to the shared Career Profile. category: one of {CATEGORY_HELP}.",
        {"category": str, "fact": str},
    )
    async def save_profile_fact(args: dict) -> dict:
        try:
            category, fact = profile.clean(args["category"], args["fact"])
        except profile.ProfileError as error:
            return fail(error)
        return ok({"saved": store.add_fact(category, fact, source=agent_id)})

    @tool(
        "update_profile_fact",
        f"Correct or extend an existing profile fact by id. category (optional): one of {CATEGORY_HELP}.",
        schema({"id": "integer", "fact": "string"}, {"category": "string"}),
    )
    async def update_profile_fact(args: dict) -> dict:
        existing = store.get_fact(int(args["id"]))
        if existing is None:
            return fail(profile.ProfileError(f"No fact with id {args['id']}."))
        try:
            category, fact = profile.clean(args.get("category") or existing["category"], args["fact"])
        except profile.ProfileError as error:
            return fail(error)
        return ok({"updated": store.update_fact(existing["id"], fact, category)})

    @tool("get_profile", "Read the current Career Profile (refreshes what's in your prompt).", {})
    async def get_profile(args: dict) -> dict:
        facts = store.list_facts()
        return ok({"facts": facts, "gaps": store.profile_gaps(facts)})

    return [save_profile_fact, update_profile_fact, get_profile]
