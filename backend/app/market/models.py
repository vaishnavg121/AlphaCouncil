"""Normalized market-data domain models for AlphaCouncil.

These models decouple the application from Alpaca SDK response types and
provide a stable, typed contract for deterministic feature computation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator


class Timeframe(StrEnum):
    """Supported bar timeframes."""

    DAY = "1Day"
    HOUR = "1Hour"


class Trend(StrEnum):
    """Deterministic trend classification."""

    STRONG_UP = "STRONG_UP"
    UP = "UP"
    NEUTRAL = "NEUTRAL"
    DOWN = "DOWN"
    STRONG_DOWN = "STRONG_DOWN"
    UNKNOWN = "UNKNOWN"


class DataQualityStatus(StrEnum):
    """Market data quality classification."""

    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"


class OHLCVBar(BaseModel):
    """A single normalized OHLCV bar."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    trade_count: int | None = None
    vwap: Decimal | None = None

    @field_validator("high", mode="before")
    @classmethod
    def _validate_high(cls, v: Decimal | float | int | str, info: object) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    @field_validator("low", mode="before")
    @classmethod
    def _validate_low(cls, v: Decimal | float | int | str, info: object) -> Decimal:
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))

    def validate_ohlc(self) -> bool:
        """Validate OHLC relationship: high >= max(open, close), low <= min(open, close)."""
        if self.high < max(self.open, self.close):
            return False
        if self.low > min(self.open, self.close):
            return False
        return True


class QuoteSnapshot(BaseModel):
    """Latest quote snapshot for a symbol."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    bid_price: Decimal
    ask_price: Decimal
    bid_size: int | None = None
    ask_size: int | None = None

    @property
    def spread(self) -> Decimal:
        return self.ask_price - self.bid_price

    @property
    def midpoint(self) -> Decimal:
        return (self.bid_price + self.ask_price) / Decimal("2")

    def is_valid(self) -> bool:
        return self.spread >= Decimal("0") and self.bid_price > Decimal("0") and self.ask_price > Decimal("0")


class TradeSnapshot(BaseModel):
    """Latest trade snapshot for a symbol."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    price: Decimal
    size: int | None = None


class MarketSnapshot(BaseModel):
    """Aggregated market snapshot combining quote, trade, and daily bars."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    quote: QuoteSnapshot | None = None
    trade: TradeSnapshot | None = None
    daily_bar: OHLCVBar | None = None
    previous_daily_bar: OHLCVBar | None = None


class TechnicalFeatures(BaseModel):
    """Deterministic technical features computed from historical bars."""

    model_config = ConfigDict(frozen=True)

    # Returns
    return_1d: Decimal | None = None
    return_5d: Decimal | None = None
    return_20d: Decimal | None = None

    # Momentum
    momentum_5d: Decimal | None = None
    momentum_20d: Decimal | None = None

    # Moving Averages
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    ema_20: Decimal | None = None
    ema_50: Decimal | None = None

    # Trend distances
    distance_sma20_pct: Decimal | None = None
    distance_sma50_pct: Decimal | None = None

    # RSI
    rsi_14: Decimal | None = None

    # ATR
    atr_14: Decimal | None = None
    atr_pct: Decimal | None = None

    # Volatility
    realized_vol_20: Decimal | None = None

    # Volume
    avg_volume_20: Decimal | None = None
    volume_ratio: Decimal | None = None
    volume_zscore: Decimal | None = None

    # Drawdown
    current_drawdown: Decimal | None = None

    # Trend classification
    trend_short: Trend = Trend.UNKNOWN
    trend_medium: Trend = Trend.UNKNOWN


class DataQuality(BaseModel):
    """Market data quality metadata."""

    model_config = ConfigDict(frozen=True)

    status: DataQualityStatus
    bars_requested: int
    bars_received: int
    missing_values: int = 0
    duplicate_bars: int = 0
    stale: bool = False
    warnings: tuple[str, ...] = ()
    history_start: datetime | None = None
    history_end: datetime | None = None


class MarketState(BaseModel):
    """Complete deterministic market state for a symbol and timeframe."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    timeframe: Timeframe

    snapshot: MarketSnapshot
    latest_bar: OHLCVBar | None = None
    features: TechnicalFeatures
    data_quality: DataQuality

    bars_used: int = 0
    history_start: datetime | None = None
    history_end: datetime | None = None
    market_open: bool | None = None