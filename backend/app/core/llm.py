import os
from datetime import date
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


def build_system_prompt(agent: Agent) -> str:
    # Rebuilt every turn so facts saved by any worker show up in every other worker's next reply.
    return "\n\n".join(
        [agent.system_prompt, profile.prompt_block(), f"Today's date: {date.today().isoformat()}."]
    )


def build_options(agent: Agent, resume: str | None) -> ClaudeAgentOptions:
    tools = [*build_profile_tools(agent.id), *agent.tools]
    mcp_servers: dict[str, Any] = {
        MCP_SERVER_NAME: create_sdk_mcp_server(name=MCP_SERVER_NAME, version="0.1.0", tools=tools)
    }
    allowed_tools = [f"mcp__{MCP_SERVER_NAME}__{t.name}" for t in tools]

    return ClaudeAgentOptions(
        model=os.environ.get("MODEL_DEFAULT", "sonnet"),
        system_prompt=build_system_prompt(agent),
        # Only the built-in tools the agent opts into (no file/shell access), and no
        # user/project settings: agents get our project tools instead of raw filesystem access.
        tools=agent.builtin_tools,
        setting_sources=[],
        mcp_servers=mcp_servers,
        allowed_tools=[*allowed_tools, *agent.builtin_tools],
        include_partial_messages=True,
        max_turns=agent.max_turns,
        resume=resume,
        # Sessions are stored per cwd, so pin it to make `resume` work wherever uvicorn starts.
        cwd=BACKEND_DIR,
    )


async def stream_agent(
    agent: Agent, prompt: str, resume: str | None = None
) -> AsyncIterator[dict[str, Any]]:
    """Run one agent turn and yield UI events: text, tool, done, error."""
    wrote_text = False
    async for message in query(prompt=prompt, options=build_options(agent, resume)):
        if isinstance(message, ResultMessage):
            if message.is_error:
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
        model=os.environ.get("MODEL_FAST", "haiku"),
        system_prompt=system_prompt,
        tools=[],
        setting_sources=[],
        max_turns=1,
        cwd=BACKEND_DIR,
    )
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            if message.is_error or not message.result:
                raise RuntimeError(message.result or message.subtype)
            return message.result
    raise RuntimeError("No result from the model")
