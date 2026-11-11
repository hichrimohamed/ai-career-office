"""Morning standup: each worker's status from their board, voiced as one line by the fast model.

The facts and the suggested next step come from the database, so the numbers are always right.
The model only rewords them; if it fails or returns something unusable, the plain facts are used.
"""

import json
import re
from datetime import date

from app.agents import AGENTS
from app.agents.base import INTERVIEW_ACTION
from app.core import llm, store

GOOD_FIT = 60
MAX_LINE_CHARS = 220
PLACEHOLDER = re.compile(r"\[(?:ADD|CONFIRM|DELETE)[^\]]*\]")
ACTIVE_JOB_STATUSES = {"applying", "applied", "interview", "offer"}

SYSTEM_PROMPT = """You voice a morning standup in a small office of AI career assistants.
For each worker you get their name, role and a list of facts. Write one standup line per worker:
first person, friendly and direct, at most 25 words, using only the given facts.
Never add numbers, names or claims that are not in the facts.
Reply with only a JSON object mapping each worker id to their line."""


def _quick_action(agent_id: str, label: str) -> dict:
    action = next(a for a in AGENTS[agent_id].quick_actions if a["label"] == label)
    return {"label": action["label"], "prompt": action["prompt"]}


def _short(title: str, limit: int = 32) -> str:
    """A title short enough for a button."""
    if len(title) <= limit:
        return title
    return title[:limit].rsplit(" ", 1)[0].rstrip(" ,:;-") + "…"


def _section_name(section: dict) -> str:
    return f"{section['section']} ({section['label']})" if section["label"] else section["section"]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def content_status() -> dict:
    drafts = store.list_drafts()
    open_drafts = sorted((d for d in drafts if d["status"] == "draft"), key=lambda d: d["id"])
    ready = [d for d in drafts if d["status"] == "ready"]
    new_ideas = [i for i in store.list_ideas() if i["status"] == "new"]

    facts = [
        f"{_plural(len(open_drafts), 'draft')} in progress",
        f"{len(ready)} ready to post",
        f"{_plural(len(new_ideas), 'new idea')} in the backlog",
    ]
    if open_drafts:
        draft = open_drafts[0]
        placeholders = len(PLACEHOLDER.findall(draft["body"]))
        if placeholders:
            facts.append(f"draft \"{draft['title']}\" still has {_plural(placeholders, 'placeholder')} to fill")
        next_step = {
            "label": f"Finish \"{_short(draft['title'])}\"",
            "prompt": f"Let's finish draft #{draft['id']} \"{draft['title']}\". Ask me for whatever is missing, "
            "one question at a time, then update the draft.",
        }
    elif ready:
        next_step = {
            "label": f"Post \"{_short(ready[0]['title'])}\"",
            "prompt": f"Draft #{ready[0]['id']} is ready. When should I post it, and what first comment should I add?",
        }
    elif new_ideas:
        idea = new_ideas[0]
        next_step = {
            "label": f"Draft \"{_short(idea['title'])}\"",
            "prompt": f"Let's turn idea #{idea['id']} \"{idea['title']}\" into a draft. Ask me what you need first.",
        }
    else:
        next_step = _quick_action("content", "Weekly brief")
    return {"facts": facts, "next": next_step}


def optimizer_status() -> dict:
    sections = store.list_sections()
    proposed = [s for s in sections if s["status"] == "proposed"]
    applied = len(sections) - len(proposed)
    missing = store.profile_gaps(store.list_facts())

    facts = [f"{_plural(len(proposed), 'rewrite')} waiting to be applied on LinkedIn", f"{applied} applied"]
    if missing:
        facts.append(f"career profile is missing: {', '.join(missing)}")
    if proposed:
        section = proposed[0]
        next_step = {
            "label": f"Apply the {_short(_section_name(section))} rewrite",
            "prompt": f"Walk me through applying the {_section_name(section)} rewrite on LinkedIn, "
            "and tell me what to check once it's live.",
        }
    elif missing:
        next_step = dict(INTERVIEW_ACTION)
    else:
        next_step = _quick_action("optimizer", "Optimize my profile")
    return {"facts": facts, "next": next_step}


def scout_status() -> dict:
    jobs = store.list_jobs()
    good = [j for j in jobs if (j["fit_score"] or 0) >= GOOD_FIT]
    active = [j for j in jobs if j["status"] in ACTIVE_JOB_STATUSES]
    unsent = [o for o in store.list_outreach() if o["status"] == "draft"]

    facts = [
        f"{_plural(len(jobs), 'job')} on the board",
        f"{_plural(len(good), 'good fit')} (score {GOOD_FIT}+)",
        f"{_plural(len(active), 'application')} in progress",
        f"{_plural(len(unsent), 'outreach note')} not sent yet",
    ]
    best = next((j for j in good if j["status"] == "saved"), None)
    if best:
        facts.append(f"best untouched fit: {best['title']} at {best['company']} ({best['fit_score']})")
        next_step = {
            "label": f"Apply to {best['company']}",
            "prompt": f"Help me apply to job #{best['id']}, {best['title']} at {best['company']}: what should I "
            "tailor in my profile, and who should I contact?",
        }
    elif unsent:
        next_step = {
            "label": "Send outreach notes",
            "prompt": "Go through my unsent outreach notes with me: which one to send first, and how to find the person.",
        }
    else:
        next_step = _quick_action("scout", "Find AI jobs")
    return {"facts": facts, "next": next_step}


def coach_status() -> dict:
    interviews = store.list_interviews()
    paused = next((i for i in interviews if i["status"] == "in_progress"), None)
    finished = next((i for i in interviews if i["status"] == "finished" and i["average_score"] is not None), None)
    open_gaps = [g for g in store.list_gaps() if g["status"] != "closed"]
    high = [g for g in open_gaps if g["severity"] == "high"]

    facts = []
    if paused:
        facts.append(
            f"mock interview #{paused['id']} paused at {len(paused['answers'])}/{paused['planned_questions']} questions"
        )
    if finished:
        facts.append(f"last finished mock interview scored {finished['average_score']}/10")
    if not interviews:
        facts.append("no mock interview yet")
    facts.append(f"{_plural(len(open_gaps), 'open skill gap')} ({len(high)} high)")

    if paused:
        next_step = {
            "label": "Resume the mock interview",
            "prompt": f"Let's resume mock interview #{paused['id']} where we stopped. Ask the next question.",
        }
    elif high:
        next_step = {
            "label": f"Close the {high[0]['skill']} gap",
            "prompt": f"Suggest a small portfolio project that closes my {high[0]['skill']} gap, and save it.",
        }
    else:
        next_step = _quick_action("coach", "Mock interview")
    return {"facts": facts, "next": next_step}


STATUS_BUILDERS = {
    "content": content_status,
    "optimizer": optimizer_status,
    "scout": scout_status,
    "coach": coach_status,
}


def plain_line(facts: list[str]) -> str:
    text = "; ".join(facts)
    return text[0].upper() + text[1:] + "."


def _parse_lines(reply: str, agent_ids: list[str]) -> dict[str, str]:
    """The model's JSON object of lines, keeping only usable ones."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return {
        agent_id: data[agent_id].strip()
        for agent_id in agent_ids
        if isinstance(data.get(agent_id), str) and 0 < len(data[agent_id].strip()) <= MAX_LINE_CHARS
    }


async def run_standup() -> list[dict]:
    statuses = {agent_id: build() for agent_id, build in STATUS_BUILDERS.items()}
    brief = {
        agent_id: {"name": AGENTS[agent_id].name, "role": AGENTS[agent_id].role, "facts": status["facts"]}
        for agent_id, status in statuses.items()
    }
    try:
        lines = _parse_lines(await llm.complete(SYSTEM_PROMPT, json.dumps(brief, indent=2)), list(statuses))
    except Exception:  # the standup still works without the model
        lines = {}

    return [
        {
            "agent_id": agent_id,
            "name": AGENTS[agent_id].name,
            "line": lines.get(agent_id) or plain_line(status["facts"]),
            "facts": status["facts"],
            "next": status["next"],
        }
        for agent_id, status in statuses.items()
    ]


async def todays_standup(refresh: bool = False) -> dict:
    """Today's standup, run once a day (or again on `refresh`) and cached."""
    day = date.today().isoformat()
    if not refresh and (cached := store.get_standup(day)):
        return cached
    return store.save_standup(day, await run_standup())
