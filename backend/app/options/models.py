"""Normalized option domain models for M5 Instrument Selection.

These models decouple the application from Alpaca SDK response types and
provide a stable, typed contract for deterministic instrument selection.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class OptionType(StrEnum):
    """Option contract type."""

    CALL = "CALL"
    PUT = "PUT"


class OptionContractStatus(StrEnum):
    """Option contract status from provider."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class OptionDataQualityStatus(StrEnum):
    """Option market data quality classification."""

    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"


class OptionContract(BaseModel):
    """Normalized option contract metadata."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    underlying_symbol: str
    option_type: OptionType
    expiration_date: date
    strike_price: Decimal
    multiplier: int = 100
    tradable: bool = True
    status: OptionContractStatus = OptionContractStatus.ACTIVE
    size: Decimal | None = None
    open_interest: int | None = None
    open_interest_date: date | None = None
    close_price: Decimal | None = None
    close_price_date: date | None = None

    @property
    def days_to_expiry(self) -> int:
        """Calculate days to expiration from today."""
        from datetime import date as date_cls
        delta = self.expiration_date - date_cls.today()
        return max(0, delta.days)

    @property
    def is_call(self) -> bool:
        return self.option_type == OptionType.CALL

    @property
    def is_put(self) -> bool:
        return self.option_type == OptionType.PUT


class OptionQuote(BaseModel):
    """Normalized option quote."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    bid_price: Decimal
    bid_size: Decimal
    ask_price: Decimal
    ask_size: Decimal

    @property
    def spread(self) -> Decimal:
        return self.ask_price - self.bid_price

    @property
    def midpoint(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")

    @property
    def spread_pct(self) -> Decimal | None:
        mid = self.midpoint
        if mid <= 0:
            return None
        return self.spread / mid

    def is_valid(self) -> bool:
        return (
            self.spread >= Decimal("0")
            and self.bid_price > Decimal("0")
            and self.ask_price > Decimal("0")
        )


class OptionTrade(BaseModel):
    """Latest option trade."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    price: Decimal
    size: Decimal


class OptionsGreeks(BaseModel):
    """Normalized option Greeks."""

    model_config = ConfigDict(frozen=True)

    delta: Decimal
    gamma: Decimal
    theta: Decimal
    vega: Decimal
    rho: Decimal


class OptionMarketSnapshot(BaseModel):
    """Complete option market snapshot."""

    model_config = ConfigDict(frozen=True)

    contract: OptionContract
    timestamp: datetime
    quote: OptionQuote | None = None
    trade: OptionTrade | None = None
    implied_volatility: Decimal | None = None
    greeks: OptionsGreeks | None = None
    underlying_price: Decimal | None = None
    data_quality: OptionDataQualityStatus = OptionDataQualityStatus.INSUFFICIENT
    warnings: tuple[str, ...] = ()

    @property
    def reference_price(self) -> Decimal | None:
        """Best available reference price for the option."""
        if self.quote and self.quote.is_valid():
            return self.quote.midpoint
        if self.trade:
            return self.trade.price
        return None

    @property
    def premium_per_contract(self) -> Decimal | None:
        """Conservative premium estimate using ask price."""
        if self.quote and self.quote.is_valid():
            return self.quote.ask_price * Decimal(str(self.contract.multiplier))
        return None

    @property
    def max_loss_per_contract(self) -> Decimal | None:
        """Maximum loss per contract (premium paid for long options)."""
        return self.premium_per_contract


class OptionDataQuality(BaseModel):
    """Option market data quality metadata."""

    model_config = ConfigDict(frozen=True)

    status: OptionDataQualityStatus
    quote_valid: bool = False
    bid_ask_valid: bool = False
    spread_pct: Decimal | None = None
    has_greeks: bool = False
    has_iv: bool = False
    underlying_price_available: bool = False
    timestamp_fresh: bool = False
    warnings: tuple[str, ...] = ()


class InstrumentNoTradeReason(StrEnum):
    """Structured reasons for NO_TRADE in instrument selection."""

    RISK_REJECTED = "RISK_REJECTED"
    MISSING_RISK_BUDGET = "MISSING_RISK_BUDGET"
    INVALID_THESIS = "INVALID_THESIS"
    NO_ELIGIBLE_EQUITY_PLAN = "NO_ELIGIBLE_EQUITY_PLAN"
    OPTIONS_UNAVAILABLE = "OPTIONS_UNAVAILABLE"
    NO_ELIGIBLE_OPTION_CONTRACT = "NO_ELIGIBLE_OPTION_CONTRACT"
    OPTION_DATA_STALE = "OPTION_DATA_STALE"
    OPTION_LIQUIDITY_POOR = "OPTION_LIQUIDITY_POOR"
    OPTION_PREMIUM_TOO_HIGH = "OPTION_PREMIUM_TOO_HIGH"
    SHORT_NOT_ALLOWED = "SHORT_NOT_ALLOWED"
    SELECTION_SCORE_TOO_LOW = "SELECTION_SCORE_TOO_LOW"
    RISK_BUDGET_TOO_SMALL = "RISK_BUDGET_TOO_SMALL"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    INTERNAL_VALIDATION_FAILED = "INTERNAL_VALIDATION_FAILED"