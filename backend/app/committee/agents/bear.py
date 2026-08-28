"""Bear Agent - constructs strongest evidence-grounded case AGAINST bullish thesis."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.models import AgentRole
from app.committee.prompts import BEAR_PROMPT_V1


class BearAgent(CommitteeAgent):
    """Bear Agent - constructs strongest evidence-grounded case AGAINST bullish thesis."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.BEAR

    @property
    def system_prompt(self) -> str:
        return BEAR_PROMPT_V1

    @property
    def _prompt_version(self) -> str:
        return "bear_v1"