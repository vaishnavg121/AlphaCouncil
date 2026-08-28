"""Quant Agent - interprets deterministic numerical evidence objectively."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.models import AgentRole
from app.committee.prompts import QUANT_PROMPT_V1


class QuantAgent(CommitteeAgent):
    """Quant Agent - interprets deterministic numerical evidence objectively."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.QUANT

    @property
    def system_prompt(self) -> str:
        return QUANT_PROMPT_V1

    @property
    def _prompt_version(self) -> str:
        return "quant_v1"