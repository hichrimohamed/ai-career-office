"""Tools for the Profile Optimizer: save section rewrites to the LinkedIn Profile board."""

from claude_agent_sdk import SdkMcpTool, tool

from app.core import linkedin, store
from app.tools.project_tools import fail, ok

SECTIONS = ", ".join(f"{name} (max {limit} chars)" for name, limit in store.LINKEDIN_SECTIONS.items())


def build_linkedin_tools(agent_id: str) -> list[SdkMcpTool]:
    @tool(
        "save_section_rewrite",
        "Save a rewrite of one LinkedIn profile section to the board, shown next to the original. "
        f"section: {SECTIONS}. label: which one, required for experience/featured (e.g. 'Software Engineer, Thales'). "
        "original: the user's current text, verbatim (empty if he has none). rewrite: exactly what he pastes into "
        "LinkedIn. rationale: why it's better, in 1-3 sentences. keywords: the search terms it targets. "
        "sources: what every claim rests on ('original', 'fact #N', 'project <name>: <file>'). "
        "Saving the same section+label again replaces the rewrite and keeps the previous one.",
        {
            "type": "object",
            "properties": {
                "section": {"type": "string"},
                "label": {"type": "string"},
                "original": {"type": "string"},
                "rewrite": {"type": "string"},
                "rationale": {"type": "string"},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["section", "rewrite", "rationale", "sources"],
        },
    )
    async def save_section_rewrite(args: dict) -> dict:
        try:
            saved = store.save_section(linkedin.clean_section(args), agent_id)
        except linkedin.SectionError as error:
            return fail(error)
        return ok({"saved": {"id": saved["id"], "section": saved["section"], "label": saved["label"],
                             "version": saved["version"], "chars": len(saved["rewrite"])}})

    @tool("list_section_rewrites", "List the LinkedIn sections already on the board, with originals and rewrites.", {})
    async def list_section_rewrites(args: dict) -> dict:
        return ok(store.list_sections())

    return [save_section_rewrite, list_section_rewrites]
