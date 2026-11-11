import os
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    create_sdk_mcp_server,
    query,
)

from app.agents.base import Agent
from app.core import profile
from app.core.store import BACKEND_DIR
from app.tools.profile_tools import build_profile_tools

MCP_SERVER_NAME = "office"


# The SDK runs on the Claude Code login, which would otherwise pull every claude.ai connector on
# the account (hundreds of tool definitions, ~175k tokens) into each agent's context.
ISOLATION_ENV = {"ENABLE_CLAUDEAI_MCP_SERVERS": "false"}
DEFAULT_TURN_BUDGET_USD = 1.0


def model_name(tier: str) -> str:
    if tier == "fast":
        return os.environ.get("MODEL_FAST", "haiku")
    return os.environ.get("MODEL_DEFAULT", "sonnet")


def turn_budget() -> float | None:
    """Spending cap for one chat message (MAX_TURN_BUDGET_USD, 0 turns it off)."""
    try:
        budget = float(os.environ.get("MAX_TURN_BUDGET_USD", DEFAULT_TURN_BUDGET_USD))
    except ValueError:
        budget = DEFAULT_TURN_BUDGET_USD
    return budget if budget > 0 else None


def build_system_prompt(agent: Agent) -> str:
    # Static on purpose: the profile and the date travel in the user turn (see app.core.sessions),
    # so this prefix stays cached when a fact is saved or the day changes.
    return "\n\n".join([agent.system_prompt, profile.PROFILE_RULES])


def build_options(
    agent: Agent, resume: str | None, tier: str = "default", spent_usd: float = 0
) -> ClaudeAgentOptions:
    tools = [*build_profile_tools(agent.id), *agent.tools]
    mcp_servers: dict[str, Any] = {
        MCP_SERVER_NAME: create_sdk_mcp_server(name=MCP_SERVER_NAME, version="0.1.0", tools=tools)
    }
    allowed_tools = [f"mcp__{MCP_SERVER_NAME}__{t.name}" for t in tools]

    return ClaudeAgentOptions(
        model=model_name(tier),
        system_prompt=build_system_prompt(agent),
        # Only the built-in tools the agent opts into (no file/shell access), and no
        # user/project settings: agents get our project tools instead of raw filesystem access.
        tools=agent.builtin_tools,
        setting_sources=[],
        mcp_servers=mcp_servers,
        # Only the office server above: no account connectors, no user or project MCP config.
        strict_mcp_config=True,
        env=ISOLATION_ENV,
        # The SDK counts cost across the whole resumed session, so the cap moves with it.
        max_budget_usd=(spent_usd + budget) if (budget := turn_budget()) else None,
        allowed_tools=[*allowed_tools, *agent.builtin_tools],
        include_partial_messages=True,
        max_turns=agent.max_turns,
        resume=resume,
        # Sessions are stored per cwd, so pin it to make `resume` work wherever uvicorn starts.
        cwd=BACKEND_DIR,
    )


def usage_of(result: ResultMessage, spent_usd: float = 0) -> dict[str, Any]:
    """This message's tokens and cost. `total_cost_usd` is a running total for a resumed session."""
    usage = result.usage or {}
    session_cost = result.total_cost_usd or 0
    return {
        "session_cost_usd": session_cost,
        "api_turns": result.num_turns or 0,
        "input_tokens": usage.get("input_tokens") or 0,
        "cache_write_tokens": usage.get("cache_creation_input_tokens") or 0,
        "cache_read_tokens": usage.get("cache_read_input_tokens") or 0,
        "output_tokens": usage.get("output_tokens") or 0,
        "cost_usd": round(max(session_cost - spent_usd, 0), 6),
    }


async def stream_agent(
    agent: Agent, prompt: str, resume: str | None = None, tier: str = "default", spent_usd: float = 0
) -> AsyncIterator[dict[str, Any]]:
    """Run one agent turn and yield events: text, tool, usage (not for the UI), then done or error."""
    wrote_text = False
    async for message in query(prompt=prompt, options=build_options(agent, resume, tier, spent_usd)):
        if isinstance(message, ResultMessage):
            yield {"type": "usage", "model": model_name(tier), "usage": usage_of(message, spent_usd)}
            if message.subtype == "error_max_budget_usd":
                yield {
                    "type": "error",
                    "message": "Stopped: this message reached its spending cap (MAX_TURN_BUDGET_USD). "
                    "Ask for a smaller step, or raise the cap in backend/.env.",
                }
            elif message.is_error:
                yield {"type": "error", "message": message.result or message.subtype}
            else:
                yield {"type": "done", "session_id": message.session_id}
            continue
        if not isinstance(message, StreamEvent) or message.parent_tool_use_id:
            continue

        event = message.event
        if event.get("type") == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "tool_use":
                yield {"type": "tool", "name": block.get("name", "")}
            elif block.get("type") == "text" and wrote_text:
                # Text after a tool call starts a new paragraph instead of running on.
                yield {"type": "text", "text": "\n\n"}
        elif event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                wrote_text = True
                yield {"type": "text", "text": delta["text"]}


async def complete(system_prompt: str, prompt: str) -> str:
    """One tool-free turn on the fast model, returning the final text. Raises if the turn fails."""
    options = ClaudeAgentOptions(
        model=model_name("fast"),
        system_prompt=system_prompt,
        tools=[],
        setting_sources=[],
        strict_mcp_config=True,
        env=ISOLATION_ENV,
        max_turns=1,
        cwd=BACKEND_DIR,
    )
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            if message.is_error or not message.result:
                raise RuntimeError(message.result or message.subtype)
            return message.result
    raise RuntimeError("No result from the model")
