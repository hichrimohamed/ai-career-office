from app.agents.base import INTERVIEW_ACTION, Agent, load_prompt
from app.tools.job_tools import build_job_tools
from app.tools.project_tools import list_recent_projects, read_project_file

SCOUT = Agent(
    id="scout",
    name="Maya",
    role="Job & People Scout",
    system_prompt=load_prompt("maya"),
    tools=[list_recent_projects, read_project_file, *build_job_tools("scout")],
    builtin_tools=["WebSearch", "WebFetch"],
    # A search run checks several postings before saving them.
    max_turns=30,
    quick_actions=[
        {
            "label": "Find AI jobs",
            "prompt": "Find 5 recent AI engineer openings that fit my profile and target location. "
            "Save them with an honest fit score.",
        },
        {
            "label": "Check a job post",
            "prompt": "Check my fit for this job post:\n\n",
            "send": False,
        },
        {
            "label": "Who to contact",
            "prompt": "For my best-fit saved job, who should I contact and what should I write? Save the notes.",
        },
        INTERVIEW_ACTION,
    ],
)
