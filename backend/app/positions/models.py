"""Position domain models for M7.

These models define the typed contracts for deterministic position monitoring
and exit management. ZERO LLM calls. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class PositionStatus(StrEnum):
    """Position lifecycle status."""

    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    PARTIALLY_EXITED = "PARTIALLY_EXITED"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ExitState(StrEnum):
    """Current exit state of a managed position."""

    NONE = "NONE"
    EXIT_PENDING = "EXIT_PENDING"
    EXITING = "EXITING"
    EXITED = "EXITED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ExitDecisionType(StrEnum):
    """Exit decision outcomes."""

    HOLD = "HOLD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class ExitReasonCode(StrEnum):
    """Structured reason codes for exit decisions."""

    # Hard exits (mandatory)
    KILL_SWITCH = "KILL_SWITCH"
    HARD_STOP_TRIGGERED = "HARD_STOP_TRIGGERED"
    MAX_LOSS_REACHED = "MAX_LOSS_REACHED"
    RISK_CONSTITUTION_VIOLATION = "RISK_CONSTITUTION_VIOLATION"
    OPTION_EXPIRY_APPROACHING = "OPTION_EXPIRY_APPROACHING"
    MAX_HOLDING_PERIOD = "MAX_HOLDING_PERIOD"
    PROVIDER_RECONCILIATION_REQUIRED = "PROVIDER_RECONCILIATION_REQUIRED"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    MANUAL_CLOSE_DETECTED = "MANUAL_CLOSE_DETECTED"

    # Soft exits (profit management)
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"

    # Thesis deterioration
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    TREND_REVERSAL = "TREND_REVERSAL"
    MOMENTUM_REVERSAL = "MOMENTUM_REVERSAL"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"

    # Portfolio risk
    PORTFOLIO_RISK_REDUCTION = "PORTFOLIO_RISK_REDUCTION"

    # Data issues
    DATA_STALE = "DATA_STALE"

    # Approved
    WITHIN_LIMITS = "WITHIN_LIMITS"


class ExitUrgency(StrEnum):
    """Exit urgency levels."""

    IMMEDIATE = "IMMEDIATE"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    NONE = "NONE"


class ManagedPosition(BaseModel):
    """Normalized managed position with full lifecycle tracking."""

    model_config = ConfigDict(frozen=True)

    position_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    instrument_type: Literal["STOCK", "ETF", "OPTION"]

    side: Literal["LONG", "SHORT"]

    entry_execution_id: str
    entry_order_id: str
    instrument_plan_id: str

    entry_timestamp: datetime
    entry_price: Decimal
    initial_quantity: Decimal
    current_quantity: Decimal

    current_price: Decimal = Decimal("0")

    initial_notional: Decimal
    current_notional: Decimal

    risk_budget_at_entry: Decimal
    constitution_version: str

    initial_stop_reference: Decimal | None = None
    current_stop_reference: Decimal | None = None

    highest_price_since_entry: Decimal | None = None
    lowest_price_since_entry: Decimal | None = None

    unrealized_pnl: Decimal = Decimal("0")
    unrealized_pnl_pct: Decimal = Decimal("0")

    realized_pnl: Decimal = Decimal("0")

    status: PositionStatus = PositionStatus.PENDING_ENTRY
    exit_state: ExitState = ExitState.NONE

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    mfe: Decimal = Decimal("0")
    mae: Decimal = Decimal("0")

    @property
    def is_open(self) -> bool:
        return self.status == PositionStatus.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == PositionStatus.CLOSED

    @property
    def is_partial_exit(self) -> bool:
        return self.status == PositionStatus.PARTIALLY_EXITED

    @property
    def is_reconciliation_required(self) -> bool:
        return self.status == PositionStatus.RECONCILIATION_REQUIRED

    @property
    def quantity_filled_pct(self) -> Decimal:
        if self.initial_quantity <= 0:
            return Decimal("0")
        return self.current_quantity / self.initial_quantity

    @property
    def pnl_pct(self) -> Decimal:
        if self.entry_price <= 0:
            return Decimal("0")
        if self.side == "LONG":
            return (self.current_price - self.entry_price) / self.entry_price
        else:
            return (self.entry_price - self.current_price) / self.entry_price

    @property
    def time_in_trade_seconds(self) -> int:
        return int((datetime.now(UTC) - self.entry_timestamp).total_seconds())

    def to_store_record(self) -> PositionStoreRecord:
        """Convert to PositionStoreRecord for persistence."""
        return PositionStoreRecord(
            position_id=self.position_id,
            symbol=self.symbol,
            instrument_type=self.instrument_type,
            side=self.side,
            entry_execution_id=self.entry_execution_id,
            entry_order_id=self.entry_order_id,
            instrument_plan_id=self.instrument_plan_id,
            entry_timestamp=self.entry_timestamp,
            entry_price=self.entry_price,
            initial_quantity=self.initial_quantity,
            current_quantity=self.current_quantity,
            current_price=self.current_price,
            initial_notional=self.initial_notional,
            current_notional=self.current_notional,
            risk_budget_at_entry=self.risk_budget_at_entry,
            constitution_version=self.constitution_version,
            initial_stop_reference=self.initial_stop_reference,
            current_stop_reference=self.current_stop_reference,
            highest_price_since_entry=self.highest_price_since_entry,
            lowest_price_since_entry=self.lowest_price_since_entry,
            unrealized_pnl=self.unrealized_pnl,
            unrealized_pnl_pct=self.unrealized_pnl_pct,
            realized_pnl=self.realized_pnl,
            status=self.status.value,
            exit_state=self.exit_state.value,
            created_at=self.created_at,
            updated_at=self.updated_at,
            mfe=self.mfe,
            mae=self.mae,
        )


class PositionSnapshot(BaseModel):
    """Fresh position snapshot with current market data and metrics."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    side: Literal["LONG", "SHORT"]
    instrument_type: Literal["STOCK", "ETF", "OPTION"]

    current_quantity: Decimal
    current_price: Decimal
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    midpoint: Decimal | None = None

    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal

    entry_price: Decimal
    entry_timestamp: datetime
    time_in_trade_seconds: int

    highest_price_since_entry: Decimal | None = None
    lowest_price_since_entry: Decimal | None = None

    initial_stop_reference: Decimal | None = None
    current_stop_reference: Decimal | None = None

    distance_to_stop_pct: Decimal | None = None
    distance_to_high_watermark_pct: Decimal | None = None
    distance_to_low_watermark_pct: Decimal | None = None

    mfe: Decimal = Decimal("0")  # Maximum Favorable Excursion
    mae: Decimal = Decimal("0")  # Maximum Adverse Excursion

    atr_at_entry: Decimal | None = None
    current_atr: Decimal | None = None
    atr_movement_pct: Decimal | None = None

    data_quality: str = "GOOD"
    snapshot_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def spread_pct(self) -> Decimal | None:
        if self.bid_price is None or self.ask_price is None or self.midpoint is None or self.midpoint <= 0:
            return None
        return (self.ask_price - self.bid_price) / self.midpoint


class ExitDecision(BaseModel):
    """Deterministic exit decision for a managed position."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    decision: ExitDecisionType
    reason_codes: tuple[ExitReasonCode, ...] = ()
    urgency: ExitUrgency = ExitUrgency.NONE

    target_quantity_to_close: Decimal = Decimal("0")
    quantity_remaining: Decimal = Decimal("0")

    reference_price: Decimal
    fresh_bid: Decimal | None = None
    fresh_ask: Decimal | None = None
    fresh_mid: Decimal | None = None

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_exit(self) -> bool:
        return self.decision == ExitDecisionType.EXIT

    @property
    def is_reduce(self) -> bool:
        return self.decision == ExitDecisionType.REDUCE

    @property
    def is_hold(self) -> bool:
        return self.decision == ExitDecisionType.HOLD

    @property
    def is_hard_exit(self) -> bool:
        hard_reasons = {
            ExitReasonCode.KILL_SWITCH,
            ExitReasonCode.HARD_STOP_TRIGGERED,
            ExitReasonCode.MAX_LOSS_REACHED,
            ExitReasonCode.RISK_CONSTITUTION_VIOLATION,
            ExitReasonCode.OPTION_EXPIRY_APPROACHING,
            ExitReasonCode.MAX_HOLDING_PERIOD,
            ExitReasonCode.PROVIDER_RECONCILIATION_REQUIRED,
            ExitReasonCode.POSITION_MISMATCH,
            ExitReasonCode.MANUAL_CLOSE_DETECTED,
        }
        return any(r in hard_reasons for r in self.reason_codes)


class ExitPlan(BaseModel):
    """Execution plan for exiting a position."""

    model_config = ConfigDict(frozen=True)

    exit_plan_id: str = Field(default_factory=lambda: str(uuid4()))
    position_id: str

    symbol: str
    instrument_type: Literal["STOCK", "ETF", "OPTION"]

    decision: ExitDecisionType
    side: Literal["SELL", "BUY_TO_COVER", "SELL_TO_CLOSE"]
    quantity: Decimal

    reason_codes: tuple[ExitReasonCode, ...] = ()
    urgency: ExitUrgency = ExitUrgency.NORMAL

    fresh_bid: Decimal | None = None
    fresh_ask: Decimal | None = None
    fresh_mid: Decimal | None = None
    reference_price: Decimal

    limit_price: Decimal | None = None
    expected_notional: Decimal

    risk_state_reference: str | None = None
    constitution_version: str = "v1.0.0"

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at


class PositionReconciliationResult(BaseModel):
    """Result of provider position reconciliation."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str

    local_quantity: Decimal
    provider_quantity: Decimal
    local_notional: Decimal
    provider_notional: Decimal

    reconciled: bool = False
    action_required: bool = False
    mismatch_detected: bool = False
    position_missing_at_provider: bool = False
    unexpected_provider_position: bool = False

    local_side: Literal["LONG", "SHORT"] | None = None
    provider_side: Literal["LONG", "SHORT"] | None = None

    details: tuple[str, ...] = ()
    reconciled_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExitExecutionResult(BaseModel):
    """Result of exit execution through M6 gateway."""

    model_config = ConfigDict(frozen=True)

    exit_plan_id: str
    position_id: str

    execution_result_id: str | None = None
    execution_status: str
    execution_order_id: str | None = None

    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None
    remaining_quantity: Decimal = Decimal("0")

    warnings: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    submitted_at: datetime | None = None
    completed_at: datetime | None = None


class PositionAuditRecord(BaseModel):
    """Audit record for position decision history."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    snapshot: PositionSnapshot
    exit_decision: ExitDecision
    exit_plan: ExitPlan | None = None
    exit_execution_result: ExitExecutionResult | None = None

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PositionStoreRecord(BaseModel):
    """Persisted position record for SQLite storage."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    symbol: str
    instrument_type: str
    side: str
    entry_execution_id: str
    entry_order_id: str
    instrument_plan_id: str

    entry_timestamp: datetime
    entry_price: Decimal
    initial_quantity: Decimal
    current_quantity: Decimal

    current_price: Decimal

    initial_notional: Decimal
    current_notional: Decimal

    risk_budget_at_entry: Decimal
    constitution_version: str

    initial_stop_reference: Decimal | None = None
    current_stop_reference: Decimal | None = None

    highest_price_since_entry: Decimal | None = None
    lowest_price_since_entry: Decimal | None = None

    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal
    realized_pnl: Decimal

    status: str
    exit_state: str

    created_at: datetime
    updated_at: datetime

    mfe: Decimal = Decimal("0")
    mae: Decimal = Decimal("0")