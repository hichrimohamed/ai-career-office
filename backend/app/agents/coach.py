from app.agents.base import INTERVIEW_ACTION, Agent, load_prompt
from app.tools.coach_tools import build_coach_tools
from app.tools.project_tools import list_recent_projects, read_project_file

COACH = Agent(
    id="coach",
    name="Kai",
    role="Career Coach",
    system_prompt=load_prompt("kai"),
    tools=[list_recent_projects, read_project_file, *build_coach_tools("coach")],
    max_turns=12,
    quick_actions=[
        {
            "label": "Mock interview",
            "prompt": "Start a 5-question mock interview for a junior-to-mid AI engineer role. "
            "Mix LLM fundamentals, RAG, evals, agents and system design.",
            "fresh": True,
        },
        {
            "label": "My skill gaps",
            "prompt": "Review my profile, saved jobs and past interviews. Update my skill gaps and suggest "
            "one portfolio project for the biggest one.",
        },
        INTERVIEW_ACTION,
    ],
)
