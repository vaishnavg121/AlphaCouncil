"""Risk domain models for M4 Deterministic Risk Constitution.

These models define the typed contracts for deterministic risk evaluation.
ZERO LLM calls. NO trading execution. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class RiskDecisionType(StrEnum):
    """Final risk decision - only three outcomes."""

    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


class RiskReasonCode(StrEnum):
    """Structured reason codes for risk decisions - exhaustive and stable."""

    # Hard gates (REJECTED)
    M3_NO_TRADE = "M3_NO_TRADE"
    INVALID_THESIS = "INVALID_THESIS"
    POOR_DATA_QUALITY = "POOR_DATA_QUALITY"
    LOW_COMMITTEE_CONFIDENCE = "LOW_COMMITTEE_CONFIDENCE"
    INVALID_PRICE = "INVALID_PRICE"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    CALCULATION_FAILURE = "CALCULATION_FAILURE"

    # Soft reductions (REDUCED)
    VOLATILITY_REDUCTION = "VOLATILITY_REDUCTION"
    LIQUIDITY_REDUCTION = "LIQUIDITY_REDUCTION"
    CONFIDENCE_REDUCTION = "CONFIDENCE_REDUCTION"
    SYMBOL_CONCENTRATION = "SYMBOL_CONCENTRATION"
    GROSS_EXPOSURE = "GROSS_EXPOSURE"
    NET_EXPOSURE = "NET_EXPOSURE"
    MAX_POSITIONS = "MAX_POSITIONS"
    GROUP_CONCENTRATION = "GROUP_CONCENTRATION"
    CORRELATION_REDUNDANCY = "CORRELATION_REDUNDANCY"

    # Approved
    WITHIN_LIMITS = "WITHIN_LIMITS"


class RiskRuleType(StrEnum):
    """Classification of risk rules."""

    HARD_GATE = "HARD_GATE"
    SOFT_REDUCTION = "SOFT_REDUCTION"


class RiskCheckResult(BaseModel):
    """Result of a single risk rule check."""

    model_config = ConfigDict(frozen=True)

    rule_name: str
    rule_type: RiskRuleType
    passed: bool
    reason_code: RiskReasonCode | None = None
    detail: str | None = None
    reduction_factor: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    @property
    def is_hard_rejection(self) -> bool:
        return self.rule_type == RiskRuleType.HARD_GATE and not self.passed

    @property
    def is_soft_reduction(self) -> bool:
        return self.rule_type == RiskRuleType.SOFT_REDUCTION and not self.passed


class NormalizedPosition(BaseModel):
    """Normalized position for risk computation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: Decimal
    market_value: Decimal
    side: Literal["long", "short"]
    entry_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None

    @property
    def notional(self) -> Decimal:
        return self.market_value

    @property
    def signed_notional(self) -> Decimal:
        return self.market_value if self.side == "long" else -self.market_value


class AccountSnapshot(BaseModel):
    """Read-only account snapshot from Alpaca (paper)."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    status: str
    currency: str
    equity: Decimal
    buying_power: Decimal
    cash: Decimal
    portfolio_value: Decimal
    initial_margin: Decimal | None = None
    maintenance_margin: Decimal | None = None
    daytrade_count: int = 0
    as_of: datetime

    @field_validator("equity", "buying_power", "cash", "portfolio_value", mode="before")
    @classmethod
    def _to_decimal(cls, v: str | Decimal | float | int | None) -> Decimal:
        if v is None:
            return Decimal("0")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))


class PortfolioSnapshot(BaseModel):
    """Read-only portfolio snapshot with normalized positions."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    positions: tuple[NormalizedPosition, ...] = ()
    as_of: datetime

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def gross_exposure(self) -> Decimal:
        total = sum((p.notional for p in self.positions), Decimal("0"))
        return total if isinstance(total, Decimal) else Decimal("0")

    @property
    def net_exposure(self) -> Decimal:
        total = sum((p.signed_notional for p in self.positions), Decimal("0"))
        return total if isinstance(total, Decimal) else Decimal("0")

    @property
    def long_exposure(self) -> Decimal:
        total = sum((p.notional for p in self.positions if p.side == "long"), Decimal("0"))
        return total if isinstance(total, Decimal) else Decimal("0")

    @property
    def short_exposure(self) -> Decimal:
        total = sum((p.notional for p in self.positions if p.side == "short"), Decimal("0"))
        return total if isinstance(total, Decimal) else Decimal("0")

    def get_position(self, symbol: str) -> NormalizedPosition | None:
        for p in self.positions:
            if p.symbol == symbol:
                return p
        return None

    def get_group_exposure(self, group_symbols: set[str]) -> Decimal:
        total = sum((p.notional for p in self.positions if p.symbol in group_symbols), Decimal("0"))
        return total if isinstance(total, Decimal) else Decimal("0")


class RiskState(BaseModel):
    """Session risk state - tracks drawdown, peak equity, daily P&L."""

    model_config = ConfigDict(frozen=True)

    session_start_equity: Decimal
    peak_equity: Decimal
    current_equity: Decimal
    daily_realized_pnl: Decimal = Decimal("0")
    daily_unrealized_pnl: Decimal = Decimal("0")
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    last_updated: datetime

    @property
    def current_drawdown(self) -> Decimal:
        if self.peak_equity <= 0:
            return Decimal("0")
        return (self.peak_equity - self.current_equity) / self.peak_equity

    @property
    def daily_pnl(self) -> Decimal:
        return self.daily_realized_pnl + self.daily_unrealized_pnl

    @property
    def daily_return(self) -> Decimal:
        if self.session_start_equity <= 0:
            return Decimal("0")
        return self.daily_pnl / self.session_start_equity

    def with_updated_equity(self, equity: Decimal, realized_pnl: Decimal | None = None, unrealized_pnl: Decimal | None = None) -> RiskState:
        new_peak = max(self.peak_equity, equity)
        return RiskState(
            session_start_equity=self.session_start_equity,
            peak_equity=new_peak,
            current_equity=equity,
            daily_realized_pnl=realized_pnl if realized_pnl is not None else self.daily_realized_pnl,
            daily_unrealized_pnl=unrealized_pnl if unrealized_pnl is not None else self.daily_unrealized_pnl,
            kill_switch_active=self.kill_switch_active,
            kill_switch_reason=self.kill_switch_reason,
            last_updated=datetime.now(),
        )

    def with_kill_switch(self, active: bool, reason: str | None = None) -> RiskState:
        return RiskState(
            session_start_equity=self.session_start_equity,
            peak_equity=self.peak_equity,
            current_equity=self.current_equity,
            daily_realized_pnl=self.daily_realized_pnl,
            daily_unrealized_pnl=self.daily_unrealized_pnl,
            kill_switch_active=active,
            kill_switch_reason=reason,
            last_updated=datetime.now(),
        )


class RiskContext(BaseModel):
    """Complete context for a single risk evaluation."""

    model_config = ConfigDict(frozen=True)

    # Input thesis
    trade_thesis: TradeThesis  # Forward ref

    # Market data
    reference_price: Decimal
    atr_14: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    spread_pct: Decimal | None = None
    avg_dollar_volume_20: Decimal | None = None
    realized_vol_20: Decimal | None = None

    # Account & portfolio
    account: AccountSnapshot
    portfolio: PortfolioSnapshot
    risk_state: RiskState

    # Constitution version
    constitution_version: str = "v1"

    @property
    def equity(self) -> Decimal:
        return self.account.equity


class RiskBudget(BaseModel):
    """Deterministic risk budget computation result."""

    model_config = ConfigDict(frozen=True)

    # Base budget
    base_risk_budget: Decimal  # equity * base_risk_per_trade

    # Reductions (multiplicative, each <= 1.0)
    confidence_reduction: Decimal = Decimal("1.0")
    volatility_reduction: Decimal = Decimal("1.0")
    liquidity_reduction: Decimal = Decimal("1.0")
    concentration_reduction: Decimal = Decimal("1.0")
    exposure_reduction: Decimal = Decimal("1.0")
    correlation_reduction: Decimal = Decimal("1.0")

    # Final adjusted budget
    adjusted_risk_budget: Decimal

    # Position sizing
    atr_stop_distance: Decimal | None = None
    max_position_notional: Decimal = Decimal("0")
    shares: int = 0

    # Limiting rule
    limiting_rule: RiskReasonCode | None = None

    @property
    def total_reduction(self) -> Decimal:
        return (
            self.confidence_reduction
            * self.volatility_reduction
            * self.liquidity_reduction
            * self.concentration_reduction
            * self.exposure_reduction
            * self.correlation_reduction
        )

    @field_validator("adjusted_risk_budget", mode="after")
    @classmethod
    def _validate_adjusted_le_base(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        base = info.data.get("base_risk_budget", Decimal("0")) if info.data else Decimal("0")
        if v > base + Decimal("0.01"):  # Small tolerance for rounding
            raise ValueError("adjusted_risk_budget must not exceed base_risk_budget")
        return v

    @field_validator("max_position_notional")
    @classmethod
    def _validate_notional_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("max_position_notional must be non-negative")
        return v


class RiskEvaluation(BaseModel):
    """Complete risk evaluation result for a trade thesis."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    decision: RiskDecisionType
    reason_code: RiskReasonCode

    # Detailed checks
    checks: tuple[RiskCheckResult, ...] = ()

    # Budget computation
    risk_budget: RiskBudget | None = None

    # Metadata
    constitution_version: str = "v1"
    evaluated_at: datetime = Field(default_factory=datetime.now)
    runtime_ms: int = 0

    @property
    def is_approved(self) -> bool:
        return self.decision == RiskDecisionType.APPROVED

    @property
    def is_reduced(self) -> bool:
        return self.decision == RiskDecisionType.REDUCED

    @property
    def is_rejected(self) -> bool:
        return self.decision == RiskDecisionType.REJECTED

    @property
    def hard_rejections(self) -> tuple[RiskCheckResult, ...]:
        return tuple(c for c in self.checks if c.is_hard_rejection)

    @property
    def soft_reductions(self) -> tuple[RiskCheckResult, ...]:
        return tuple(c for c in self.checks if c.is_soft_reduction)

    def get_primary_reason(self) -> RiskReasonCode:
        """Get the primary reason for the decision."""
        if self.hard_rejections:
            return self.hard_rejections[0].reason_code or RiskReasonCode.CALCULATION_FAILURE
        if self.soft_reductions:
            return self.soft_reductions[0].reason_code or RiskReasonCode.WITHIN_LIMITS
        return RiskReasonCode.WITHIN_LIMITS


# Forward reference resolution
from app.committee.models import TradeThesis  # noqa: E402

RiskContext.model_rebuild()