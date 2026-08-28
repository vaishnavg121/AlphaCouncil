"""Bull Agent - constructs strongest evidence-grounded case FOR directional exposure."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.models import AgentRole
from app.committee.prompts import BULL_PROMPT_V1


class BullAgent(CommitteeAgent):
    """Bull Agent - constructs strongest evidence-grounded case FOR directional exposure."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.BULL

    @property
    def system_prompt(self) -> str:
        return BULL_PROMPT_V1

    @property
    def _prompt_version(self) -> str:
        return "bull_v1"