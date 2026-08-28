"""Instrument selection output models for M5.

These models represent the final instrument selection decision and
planning details. They are NOT order requests.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.options.models import OptionContract, OptionMarketSnapshot, OptionType
from app.risk.models import RiskEvaluation


class InstrumentType(StrEnum):
    """Type of instrument selected."""

    STOCK = "STOCK"
    ETF = "ETF"
    OPTION = "OPTION"
    NO_TRADE = "NO_TRADE"


class EquitySide(StrEnum):
    """Equity position side."""

    LONG = "LONG"
    SHORT = "SHORT"


class EquityInstrumentPlan(BaseModel):
    """Equity (stock/ETF) instrument plan."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    side: EquitySide
    reference_price: Decimal
    max_notional: Decimal
    planned_notional: Decimal
    estimated_quantity: Decimal
    fractional_supported: bool = False
    risk_budget_used: Decimal
    estimated_loss_at_risk_stop: Decimal
    selection_score: Decimal
    selection_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class OptionInstrumentPlan(BaseModel):
    """Option instrument plan."""

    model_config = ConfigDict(frozen=True)

    contract_symbol: str
    underlying_symbol: str
    option_type: OptionType
    expiration_date: datetime
    days_to_expiry: int
    strike_price: Decimal
    bid_price: Decimal
    ask_price: Decimal
    midpoint: Decimal
    spread: Decimal
    spread_pct: Decimal
    implied_volatility: Optional[Decimal] = None
    delta: Optional[Decimal] = None
    gamma: Optional[Decimal] = None
    theta: Optional[Decimal] = None
    vega: Optional[Decimal] = None
    premium_per_contract: Decimal
    multiplier: int
    planned_contracts: int
    total_premium: Decimal
    maximum_loss: Decimal
    risk_budget_used: Decimal
    selection_score: Decimal
    selection_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class InstrumentPlan(BaseModel):
    """Complete instrument selection result."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    symbol: str
    thesis_direction: Literal["BULLISH", "BEARISH"]
    instrument_type: InstrumentType
    underlying_symbol: Optional[str] = None
    risk_evaluation_id: Optional[str] = None
    constitution_version: str = "v1.0.0"
    equity_plan: Optional[EquityInstrumentPlan] = None
    option_plan: Optional[OptionInstrumentPlan] = None
    no_trade_reason: Optional[str] = None
    selection_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_stock(self) -> bool:
        return self.instrument_type in (InstrumentType.STOCK, InstrumentType.ETF)

    @property
    def is_option(self) -> bool:
        return self.instrument_type == InstrumentType.OPTION

    @property
    def is_no_trade(self) -> bool:
        return self.instrument_type == InstrumentType.NO_TRADE

    @property
    def max_loss(self) -> Decimal:
        if self.option_plan:
            return self.option_plan.maximum_loss
        if self.equity_plan:
            return self.equity_plan.estimated_loss_at_risk_stop
        return Decimal("0")

    @property
    def risk_budget_used(self) -> Decimal:
        if self.option_plan:
            return self.option_plan.risk_budget_used
        if self.equity_plan:
            return self.equity_plan.risk_budget_used
        return Decimal("0")


class OptionRejectionSummary(BaseModel):
    """Summary of option contract rejections for observability."""

    model_config = ConfigDict(frozen=True)

    total_retrieved: int = 0
    expired_out_of_range: int = 0
    spread_too_wide: int = 0
    premium_too_high: int = 0
    invalid_quote: int = 0
    invalid_greeks: int = 0
    delta_out_of_range: int = 0
    moneyness_out_of_range: int = 0
    zero_bid: int = 0
    non_tradable: int = 0
    other: int = 0

    @property
    def total_rejected(self) -> int:
        return (
            self.expired_out_of_range
            + self.spread_too_wide
            + self.premium_too_high
            + self.invalid_quote
            + self.invalid_greeks
            + self.delta_out_of_range
            + self.moneyness_out_of_range
            + self.zero_bid
            + self.non_tradable
            + self.other
        )

    @property
    def eligible_count(self) -> int:
        return max(0, self.total_retrieved - self.total_rejected)