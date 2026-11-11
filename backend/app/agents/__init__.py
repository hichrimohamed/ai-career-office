from app.agents.base import Agent
from app.agents.coach import COACH
from app.agents.content import CONTENT
from app.agents.optimizer import OPTIMIZER
from app.agents.scout import SCOUT

# Order sets the desk each worker sits at.
AGENTS: dict[str, Agent] = {agent.id: agent for agent in [CONTENT, OPTIMIZER, SCOUT, COACH]}

__all__ = ["AGENTS", "Agent"]
