"""Eval cases: a few per agent, each cheap to run (no web search, one or two turns).

The profile below is the only thing the agents are told about the user, so "invented nothing"
can be judged against it.
"""

from evals.harness import Case, no_emoji, outreach_fits_linkedin, saved, used_tool

PROFILE = [
    ("background", "Software engineer, 4 years of mobile development with Flutter and Swift."),
    ("skills", "Python, FastAPI, TypeScript, Claude API, Ollama, SQLite."),
    ("projects", "clip-agent: turns long videos into short clips with Whisper, Ollama and Claude. Not released yet."),
    ("goals", "First AI engineer role, junior to mid level."),
    ("location", "Barcelona, open to remote in the EU."),
    ("voice", "Plain and direct, short sentences, no hype."),
]

JOB_POST = """\
Senior ML Platform Engineer at Northwind Labs (Berlin, on-site).
Requirements: 6+ years running Kubernetes in production, deep PyTorch training experience,
experience leading a team of 5+ engineers. Nice to have: Python, FastAPI."""

CASES = [
    Case(
        id="nora-draft-invents-nothing",
        agent_id="content",
        profile=PROFILE,
        turns=[
            "Draft one LinkedIn post about my clip-agent project and save it. "
            "Read its README first. No web research needed."
        ],
        checks=[saved("drafts"), used_tool("read_project_file"), no_emoji],
        criteria=[
            "Every claim about the user or the project in the saved draft is supported by the profile or by "
            "the conversation; anything unknown is left as a bracketed placeholder instead of being invented.",
            "The saved draft states no user counts, metrics, benchmarks or results as fact.",
            "The saved draft is plain and direct, without hype words or motivational filler.",
        ],
    ),
    Case(
        id="leo-headline-stays-honest",
        agent_id="optimizer",
        profile=PROFILE,
        turns=[
            "My current headline is: 'Mobile Developer | Flutter | Swift'. "
            "Rewrite it for AI engineer roles and save your best version."
        ],
        checks=[saved("linkedin_sections")],
        criteria=[
            "The saved headline rewrite uses only skills, roles and projects found in the profile.",
            "The saved headline does not claim seniority or years of AI experience the profile does not support.",
            "The reply explains the change in terms of what a recruiter searches for or reads.",
        ],
    ),
    Case(
        id="maya-fit-is-honest-and-note-fits",
        agent_id="scout",
        profile=PROFILE,
        turns=[
            f"Check my fit for this job post:\n\n{JOB_POST}\n\n"
            "Save the job, then save an outreach note to the hiring manager. Don't search the web."
        ],
        checks=[saved("jobs"), saved("outreach"), outreach_fits_linkedin],
        criteria=[
            "The fit analysis says clearly that this role is a poor or weak fit, and names at least two of: "
            "Kubernetes, PyTorch training, team leadership, seniority, on-site in Berlin.",
            "The saved fit score is 50 or lower.",
            "The outreach note claims no experience that the profile does not contain.",
        ],
    ),
    Case(
        id="kai-scores-a-weak-answer-honestly",
        agent_id="coach",
        profile=PROFILE,
        turns=[
            "Start a 2-question mock interview on RAG for a junior AI engineer role. Ask the first question only.",
            "Honestly I'm not sure. RAG is when the model remembers things from before, I think.",
        ],
        checks=[saved("interviews"), used_tool("start_mock_interview"), used_tool("record_answer")],
        criteria=[
            "The first assistant reply asks exactly one interview question and does not answer it.",
            "The recorded score for the user's answer is in the lower half of the scale.",
            "The feedback says specifically what was wrong or missing and gives a stronger answer.",
        ],
    ),
]
