from app.agents.base import Agent, load_prompt
from app.tools.linkedin_tools import build_linkedin_tools
from app.tools.project_tools import list_recent_projects, read_project_file

OPTIMIZER = Agent(
    id="optimizer",
    name="Leo",
    role="Profile Optimizer",
    system_prompt=load_prompt("leo"),
    tools=[list_recent_projects, read_project_file, *build_linkedin_tools("optimizer")],
    builtin_tools=["WebSearch"],
    max_turns=20,
    quick_actions=[
        {
            "label": "Optimize my profile",
            "prompt": "I want my LinkedIn profile to get me AI engineer interviews. What should I paste first?",
        },
        {
            "label": "Headline options",
            "prompt": "Based on what you know about me, propose 3 headline options and save the best one.",
        },
    ],
)
