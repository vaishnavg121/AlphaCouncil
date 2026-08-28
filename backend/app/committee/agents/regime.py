"""Regime Agent - judges compatibility between candidate and observed market-state regime."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.models import AgentRole
from app.committee.prompts import REGIME_PROMPT_V1


class RegimeAgent(CommitteeAgent):
    """Regime Agent - judges compatibility between candidate and observed market-state regime."""

    @property
    def role(self) -> AgentRole:
        return AgentRole.REGIME

    @property
    def system_prompt(self) -> str:
        return REGIME_PROMPT_V1

    @property
    def _prompt_version(self) -> str:
        return "regime_v1"