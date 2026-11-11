"""Which session a chat message runs in, and what context travels with it.

An agent keeps one session per day. Heavy quick actions (weekly brief, job search, mock interview)
start a new one, so yesterday's tool results are not re-sent with every message. The profile and
the date are added to the user turn only when they changed since this session last saw them.
"""

import hashlib
from dataclasses import dataclass
from datetime import date

from app.agents.base import Agent
from app.core import profile, store

RECENT_MESSAGES = 6
RECENT_MESSAGE_CHARS = 1_200


@dataclass(frozen=True)
class Turn:
    prompt: str
    resume: str | None
    tier: str  # "default" or "fast"
    day: str
    context_hash: str
    spent_usd: float = 0  # what the resumed session has cost so far (the SDK reports a running total)


def recent_conversation(agent: Agent) -> str:
    """The tail of the chat the user still sees on screen, for a session that starts without it."""
    messages = store.list_messages(agent.id)[-RECENT_MESSAGES:]
    if not messages:
        return ""
    lines = ["### Earlier in this chat (most recent last)"]
    for message in messages:
        speaker = "User" if message["role"] == "user" else agent.name
        content = message["content"]
        if len(content) > RECENT_MESSAGE_CHARS:
            content = content[:RECENT_MESSAGE_CHARS] + " [...]"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def plan_turn(agent: Agent, message: str) -> Turn:
    """Call before the new message is stored, so it isn't echoed back as earlier conversation."""
    today = date.today().isoformat()
    action = agent.quick_action(message) or {}
    saved = store.get_session(agent.id)
    wants_own_session = bool(action.get("fresh") or action.get("model"))
    fresh = saved is None or saved["day"] != today or wants_own_session

    context = profile.context_block()
    context_hash = hashlib.sha256(context.encode()).hexdigest()[:16]

    if fresh:
        resume, tier, day, spent = None, action.get("model", "default"), today, 0.0
        if not wants_own_session:
            earlier = recent_conversation(agent)
            if earlier:
                context = f"{context}\n\n{earlier}"
    else:
        resume, tier, day, spent = saved["session_id"], saved["model"], saved["day"], saved["cost_usd"]

    if fresh or saved["context_hash"] != context_hash:
        prompt = f"<office_context>\n{context}\n</office_context>\n\n{message}"
    else:
        prompt = message
    return Turn(prompt=prompt, resume=resume, tier=tier, day=day, context_hash=context_hash, spent_usd=spent)
