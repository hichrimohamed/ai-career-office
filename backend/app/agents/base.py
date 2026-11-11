from dataclasses import dataclass, field
from pathlib import Path

from claude_agent_sdk import SdkMcpTool

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


INTERVIEW_ACTION = {
    "label": "Interview me",
    "prompt": "Interview me to fill the gaps in my Career Profile. One question at a time.",
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
    quick_actions: list[dict[str, str]] = field(default_factory=lambda: [INTERVIEW_ACTION])
