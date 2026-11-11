from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import SdkMcpTool

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


# Quick actions may carry two cost hints:
#   "fresh": True   -> start a new session instead of resuming the day's thread
#   "model": "fast" -> run that session on MODEL_FAST (implies a session of its own)
INTERVIEW_ACTION: dict[str, Any] = {
    "label": "Interview me",
    "prompt": "Interview me to fill the gaps in my Career Profile. One question at a time.",
    "fresh": True,
    "model": "fast",
}


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    role: str
    system_prompt: str
    tools: list[SdkMcpTool] = field(default_factory=list)
    # Built-in Claude Code tools this agent may use, e.g. "WebSearch". Everything else stays off.
    builtin_tools: list[str] = field(default_factory=list)
    max_turns: int = 6
    # Buttons in this worker's chat panel: {"label", "prompt"}, plus "send": False to only fill the input box.
    quick_actions: list[dict[str, Any]] = field(default_factory=lambda: [INTERVIEW_ACTION])

    def quick_action(self, message: str) -> dict[str, Any] | None:
        """The quick action this message came from, if it is one sent as is."""
        for action in self.quick_actions:
            if action.get("send", True) and action["prompt"] == message:
                return action
        return None
