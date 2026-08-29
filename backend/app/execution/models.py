"""Execution domain models for M6.

These models define the typed contracts for deterministic execution planning
and result tracking. ZERO LLM calls. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStatus(StrEnum):
    """Execution lifecycle status - exhaustive and stable."""

    PLANNED = "PLANNED"
    AUTHORIZED = "AUTHORIZED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"
    EXPIRED = "EXPIRED"
    NOT_EXECUTED = "NOT_EXECUTED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"
    PENDING_NEW = "PENDING_NEW"
    ACCEPTED = "ACCEPTED"
    NEW = "NEW"


class ExecutionAuthorizationState(StrEnum):
    """Execution authorization outcome."""

    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"


class ExecutionReasonCode(StrEnum):
    """Structured reason codes for execution decisions - exhaustive and stable."""

    # Configuration / mode
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    NOT_PAPER_MODE = "NOT_PAPER_MODE"
    LIVE_FLAG_ACTIVE = "LIVE_FLAG_ACTIVE"

    # Upstream gates
    UPSTREAM_NO_TRADE = "UPSTREAM_NO_TRADE"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_BUDGET_MISSING = "RISK_BUDGET_MISSING"
    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"

    # Market validation
    MARKET_CLOSED = "MARKET_CLOSED"
    STALE_QUOTE = "STALE_QUOTE"
    INVALID_QUOTE = "INVALID_QUOTE"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    PRICE_MOVED_TOO_FAR = "PRICE_MOVED_TOO_FAR"
    ASSET_NOT_TRADABLE = "ASSET_NOT_TRADABLE"
    ASSET_NOT_SHORTABLE = "ASSET_NOT_SHORTABLE"

    # Plan validation
    PLAN_EXPIRED = "PLAN_EXPIRED"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    NOTIONAL_EXCEEDED = "NOTIONAL_EXCEEDED"
    RISK_BUDGET_EXCEEDED = "RISK_BUDGET_EXCEEDED"

    # Duplicate protection
    DUPLICATE_EXECUTION = "DUPLICATE_EXECUTION"
    ORDER_ALREADY_EXISTS = "ORDER_ALREADY_EXISTS"

    # Provider
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INTERNAL_VALIDATION_FAILED = "INTERNAL_VALIDATION_FAILED"

    # Approved
    WITHIN_LIMITS = "WITHIN_LIMITS"


class OrderType(StrEnum):
    """Supported order types for M6."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"


class TimeInForce(StrEnum):
    """Supported time-in-force for M6."""

    DAY = "DAY"
    GTC = "GTC"


class OrderSide(StrEnum):
    """Order side."""

    BUY = "BUY"
    SELL = "SELL"


class PositionIntent(StrEnum):
    """Position intent for options."""

    BUY_TO_OPEN = "BUY_TO_OPEN"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"


class InstrumentType(StrEnum):
    """Instrument type being executed."""

    STOCK = "STOCK"
    ETF = "ETF"
    OPTION = "OPTION"


class ExecutionPlan(BaseModel):
    """Complete execution plan derived from InstrumentPlan + fresh market data."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: str = Field(default_factory=lambda: str(uuid4()))
    instrument_plan_id: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    symbol: str
    instrument_type: InstrumentType
    direction: Literal["BULLISH", "BEARISH"]

    side: OrderSide
    quantity: Decimal

    order_type: OrderType
    time_in_force: TimeInForce

    m5_reference_price: Decimal

    fresh_bid: Decimal
    fresh_ask: Decimal
    fresh_mid: Decimal
    fresh_quote_timestamp: datetime

    limit_price: Decimal

    expected_notional: Decimal

    risk_budget: Decimal
    max_authorized_notional: Decimal

    constitution_version: str

    warnings: tuple[str, ...] = ()
    reason_codes: tuple[ExecutionReasonCode, ...] = ()

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    @property
    def spread_pct(self) -> Decimal:
        if self.fresh_mid <= 0:
            return Decimal("0")
        return (self.fresh_ask - self.fresh_bid) / self.fresh_mid

    @property
    def price_deviation_pct(self) -> Decimal:
        if self.m5_reference_price <= 0:
            return Decimal("0")
        return abs(self.fresh_mid - self.m5_reference_price) / self.m5_reference_price


class ExecutionAuthorization(BaseModel):
    """Authorization result for an execution plan."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: str
    state: ExecutionAuthorizationState
    reason_code: ExecutionReasonCode

    checks: tuple[str, ...] = ()
    authorized_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_authorized(self) -> bool:
        return self.state == ExecutionAuthorizationState.AUTHORIZED


class ExecutionOrder(BaseModel):
    """Normalized order representation from provider."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    client_order_id: str

    symbol: str
    side: OrderSide
    quantity: Decimal

    order_type: OrderType
    time_in_force: TimeInForce
    limit_price: Decimal | None = None

    status: ExecutionStatus

    submitted_at: datetime
    filled_at: datetime | None = None

    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Decimal | None = None

    provider_status: str

    @property
    def is_filled(self) -> bool:
        return self.status == ExecutionStatus.FILLED

    @property
    def is_active(self) -> bool:
        return self.status in (
            ExecutionStatus.SUBMITTED,
            ExecutionStatus.PARTIALLY_FILLED,
            ExecutionStatus.PENDING_NEW,
            ExecutionStatus.ACCEPTED,
            ExecutionStatus.NEW,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ExecutionStatus.FILLED,
            ExecutionStatus.CANCELED,
            ExecutionStatus.EXPIRED,
            ExecutionStatus.REJECTED,
        )


class ExecutionResult(BaseModel):
    """Complete execution result."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: str
    instrument_plan_id: str

    status: ExecutionStatus
    authorization: ExecutionAuthorization

    execution_plan: ExecutionPlan
    execution_order: ExecutionOrder | None = None

    warnings: tuple[str, ...] = ()
    reason_codes: tuple[ExecutionReasonCode, ...] = ()

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    authorized_at: datetime | None = None
    submitted_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            ExecutionStatus.FILLED,
            ExecutionStatus.CANCELED,
            ExecutionStatus.EXPIRED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.NOT_EXECUTED,
            ExecutionStatus.FAILED,
        )

    @property
    def was_submitted(self) -> bool:
        return self.status in (
            ExecutionStatus.SUBMITTED,
            ExecutionStatus.PARTIALLY_FILLED,
            ExecutionStatus.FILLED,
            ExecutionStatus.CANCELED,
            ExecutionStatus.EXPIRED,
            ExecutionStatus.REJECTED,
        )

    @property
    def was_filled(self) -> bool:
        return self.status == ExecutionStatus.FILLED


class IdempotencyKey(BaseModel):
    """Deterministic idempotency key for execution deduplication."""

    model_config = ConfigDict(frozen=True)

    instrument_plan_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    risk_authorization_version: str

    def to_string(self) -> str:
        plan_part = self.instrument_plan_id[:8]
        version_part = self.risk_authorization_version[:8]
        return (
            f"ac-{plan_part}-{self.symbol}-{self.side.value}"
            f"-{self.quantity}-{version_part}"
        )


class ClientOrderId(BaseModel):
    """Alpaca client_order_id for duplicate protection."""

    model_config = ConfigDict(frozen=True)

    idempotency_key: str

    def to_string(self) -> str:
        # Alpaca client_order_id max 64 chars, alphanumeric + dash/underscore
        base = self.idempotency_key.replace("ac-", "")
        return f"ac-{base}"[:64]


class ExecutionStoreRecord(BaseModel):
    """Persisted execution record."""

    model_config = ConfigDict(frozen=True)

    execution_plan_id: str
    instrument_plan_id: str
    idempotency_key: str
    client_order_id: str

    authorization_state: ExecutionAuthorizationState
    provider_order_id: str | None = None
    provider_status: str | None = None

    created_at: datetime
    submitted_at: datetime | None = None
    updated_at: datetime

    @property
    def is_pending(self) -> bool:
        return (
            self.authorization_state == ExecutionAuthorizationState.AUTHORIZED
            and self.provider_order_id is None
        )


class ExecutionReconciliationResult(BaseModel):
    """Result of crash recovery reconciliation."""

    model_config = ConfigDict(frozen=True)

    local_record: ExecutionStoreRecord
    provider_order: ExecutionOrder | None = None
    reconciled: bool = False
    action_taken: str = ""