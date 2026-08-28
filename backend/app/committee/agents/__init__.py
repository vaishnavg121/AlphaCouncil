"""Agent package for M3 committee."""

from __future__ import annotations

from app.committee.agents.base import CommitteeAgent
from app.committee.agents.quant import QuantAgent
from app.committee.agents.bull import BullAgent
from app.committee.agents.bear import BearAgent
from app.committee.agents.regime import RegimeAgent

__all__ = [
    "CommitteeAgent",
    "QuantAgent",
    "BullAgent",
    "BearAgent",
    "RegimeAgent",
]