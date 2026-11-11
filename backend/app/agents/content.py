from app.agents.base import INTERVIEW_ACTION, Agent, load_prompt
from app.tools.draft_tools import build_draft_tools
from app.tools.project_tools import PROJECT_TOOLS

CONTENT = Agent(
    id="content",
    name="Nora",
    role="Content Strategist",
    system_prompt=f"{load_prompt('nora')}\n\n{load_prompt('nora_office')}",
    tools=[*PROJECT_TOOLS, *build_draft_tools("content")],
    builtin_tools=["WebSearch", "WebFetch"],
    # A weekly brief scans several projects and searches the web before writing.
    max_turns=30,
    quick_actions=[INTERVIEW_ACTION, {"label": "Weekly brief", "prompt": "Write this week's brief."}],
)
