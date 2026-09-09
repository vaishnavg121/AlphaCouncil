"""Instruments package for M5 Instrument Selection."""

from __future__ import annotations

from typing import Any

from app.instruments.models import (
    EquityInstrumentPlan,
    EquitySide,
    InstrumentPlan,
    InstrumentType,
    OptionInstrumentPlan,
    OptionRejectionSummary,
)
from app.instruments.stock import EquityPlanner


# Lazy import to avoid circular dependency
def __getattr__(name: str) -> Any:
    if name == "InstrumentSelectorService":
        from app.instruments.selector import InstrumentSelectorService
        return InstrumentSelectorService
    raise AttributeError(f"module 'app.instruments' has no attribute {name}")

__all__ = [
    "InstrumentPlan",
    "InstrumentType",
    "EquityInstrumentPlan",
    "OptionInstrumentPlan",
    "EquitySide",
    "OptionRejectionSummary",
    "InstrumentSelectorService",
    "EquityPlanner",
]
