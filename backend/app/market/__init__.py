"""Market data module for AlphaCouncil."""

from __future__ import annotations

from app.market.alpaca_gateway import AlpacaMarketDataGateway
from app.market.gateway import MarketDataError, MarketDataGateway
from app.market.indicators import (
    atr,
    avg_volume,
    classify_trend,
    compute_all_indicators,
    distance_from_sma_pct,
    drawdown,
    ema,
    momentum,
    realized_volatility,
    returns,
    rsi,
    sma,
    volume_ratio,
    volume_zscore,
)
from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    OHLCVBar,
    QuoteSnapshot,
    TechnicalFeatures,
    Timeframe,
    TradeSnapshot,
    Trend,
)
from app.market.state import InsufficientDataError, MarketStateBuilder

__all__ = [
    "MarketDataGateway",
    "AlpacaMarketDataGateway",
    "MarketDataError",
    "OHLCVBar",
    "QuoteSnapshot",
    "TradeSnapshot",
    "MarketSnapshot",
    "TechnicalFeatures",
    "DataQuality",
    "DataQualityStatus",
    "MarketState",
    "Timeframe",
    "Trend",
    "MarketStateBuilder",
    "InsufficientDataError",
    "returns",
    "momentum",
    "sma",
    "ema",
    "rsi",
    "atr",
    "realized_volatility",
    "avg_volume",
    "volume_ratio",
    "volume_zscore",
    "drawdown",
    "distance_from_sma_pct",
    "classify_trend",
    "compute_all_indicators",
]