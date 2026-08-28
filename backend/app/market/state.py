"""Market State Builder - constructs complete MarketState from market data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.market.gateway import MarketDataGateway
from app.market.indicators import compute_all_indicators
from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    OHLCVBar,
    TechnicalFeatures,
    Timeframe,
    Trend,
)


class InsufficientDataError(RuntimeError):
    """Raised when there is insufficient market data to build a valid MarketState."""

    def __init__(self, message: str, bars_received: int, bars_required: int):
        super().__init__(message)
        self.bars_received = bars_received
        self.bars_required = bars_required


class MarketStateBuilder:
    """Build MarketState objects from market data.

    Responsibilities:
    1. Normalize symbol
    2. Retrieve historical bars
    3. Retrieve current snapshot
    4. Validate data
    5. Calculate deterministic features
    6. Determine data quality
    7. Produce MarketState
    """

    DEFAULT_LOOKBACK_DAYS = 150  # Sufficient for SMA50 + buffer
    MIN_BARS_FOR_FEATURES = 50   # Minimum for SMA50

    def __init__(
        self,
        gateway: MarketDataGateway,
        settings: Settings | None = None,
        default_lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        self._gateway = gateway
        self._settings = settings or Settings()
        self._default_lookback_days = default_lookback_days

    def build(
        self,
        symbol: str,
        timeframe: Timeframe = Timeframe.DAY,
        lookback_days: int | None = None,
    ) -> MarketState:
        """Build a complete MarketState for the given symbol and timeframe.

        Args:
            symbol: Trading symbol (e.g., "AAPL").
            timeframe: Bar timeframe (default: 1Day).
            lookback_days: Number of calendar days to look back (default: 150).

        Returns:
            Complete MarketState with snapshot, features, and data quality.

        Raises:
            InsufficientDataError: If insufficient bars are available.
            MarketDataError: If market data retrieval fails.
        """
        symbol = self._normalize_symbol(symbol)
        lookback = lookback_days or self._default_lookback_days

        # Calculate date range
        end = datetime.now(UTC)
        start = end - timedelta(days=lookback)

        # Retrieve historical bars
        bars = self._gateway.get_bars(symbol, timeframe, start, end)

        # Validate and clean bars
        bars, data_quality = self._validate_bars(bars, symbol, lookback)

        if len(bars) < self.MIN_BARS_FOR_FEATURES:
            raise InsufficientDataError(
                f"Insufficient bars for {symbol}: got {len(bars)}, need at least {self.MIN_BARS_FOR_FEATURES}",
                bars_received=len(bars),
                bars_required=self.MIN_BARS_FOR_FEATURES,
            )

        # Retrieve current snapshot
        snapshot = self._gateway.get_snapshot(symbol)

        # Get latest bar
        latest_bar = bars[-1] if bars else None

        # Get current price (prefer snapshot trade, then quote midpoint, then latest bar close)
        current_price = self._get_current_price(snapshot, latest_bar)

        # Compute indicators
        indicators = compute_all_indicators(bars, current_price)

        # Build features
        features = self._build_features(indicators)

        # Determine market open status (from trading client if available)
        market_open = self._get_market_open()

        return MarketState(
            symbol=symbol,
            as_of=datetime.now(UTC),
            timeframe=timeframe,
            snapshot=snapshot,
            latest_bar=latest_bar,
            features=features,
            data_quality=data_quality,
            bars_used=len(bars),
            history_start=bars[0].timestamp if bars else None,
            history_end=bars[-1].timestamp if bars else None,
            market_open=market_open,
        )

    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol to uppercase."""
        return symbol.strip().upper()

    def _validate_bars(
        self,
        bars: list[OHLCVBar],
        symbol: str,
        lookback_days: int,
    ) -> tuple[list[OHLCVBar], DataQuality]:
        """Validate and clean historical bars."""
        warnings = []
        missing_values = 0
        duplicate_bars = 0

        if not bars:
            return [], DataQuality(
                status=DataQualityStatus.INSUFFICIENT,
                bars_requested=lookback_days,
                bars_received=0,
                warnings=("No bars returned",),
            )

        # Check for duplicate timestamps
        seen_timestamps = set()
        unique_bars = []
        for bar in bars:
            ts = bar.timestamp
            if ts in seen_timestamps:
                duplicate_bars += 1
                warnings.append(f"Duplicate timestamp {ts} for {symbol}")
            else:
                seen_timestamps.add(ts)
                unique_bars.append(bar)

        # Validate OHLC relationships
        for bar in unique_bars:
            if not bar.validate_ohlc():
                missing_values += 1
                warnings.append(f"Invalid OHLC for {symbol} at {bar.timestamp}")

        # Check for gaps (missing trading days)
        expected_bars = min(lookback_days, 252)  # Approximate trading days
        if len(unique_bars) < expected_bars * 0.8:  # Allow 20% gap tolerance
            warnings.append(f"Possible missing bars: expected ~{expected_bars}, got {len(unique_bars)}")

        # Determine status
        if missing_values > len(unique_bars) * 0.1:  # >10% invalid
            status = DataQualityStatus.DEGRADED
        elif len(unique_bars) < self.MIN_BARS_FOR_FEATURES:
            status = DataQualityStatus.INSUFFICIENT
        elif duplicate_bars > 0 or missing_values > 0:
            status = DataQualityStatus.DEGRADED
        else:
            status = DataQualityStatus.GOOD

        data_quality = DataQuality(
            status=status,
            bars_requested=lookback_days,
            bars_received=len(unique_bars),
            missing_values=missing_values,
            duplicate_bars=duplicate_bars,
            warnings=tuple(warnings) if warnings else (),
            history_start=unique_bars[0].timestamp if unique_bars else None,
            history_end=unique_bars[-1].timestamp if unique_bars else None,
        )

        return unique_bars, data_quality

    def _get_current_price(
        self,
        snapshot: MarketSnapshot,
        latest_bar: OHLCVBar | None,
    ) -> Decimal:
        """Get the best available current price."""
        # Prefer latest trade price
        if snapshot.trade is not None:
            return snapshot.trade.price
        # Then quote midpoint
        if snapshot.quote is not None and snapshot.quote.is_valid():
            return snapshot.quote.midpoint
        # Fall back to latest bar close
        if latest_bar is not None:
            return latest_bar.close
        # Last resort
        return Decimal("0")

    def _build_features(self, indicators: dict[str, Decimal | str | None]) -> TechnicalFeatures:
        """Build TechnicalFeatures from computed indicators."""
        # Helper to extract only Decimal values
        def get_decimal(key: str) -> Decimal | None:
            val = indicators.get(key)
            if isinstance(val, Decimal):
                return val
            return None

        return TechnicalFeatures(
            return_1d=get_decimal("return_1d"),
            return_5d=get_decimal("return_5d"),
            return_20d=get_decimal("return_20d"),
            momentum_5d=get_decimal("momentum_5d"),
            momentum_20d=get_decimal("momentum_20d"),
            sma_20=get_decimal("sma_20"),
            sma_50=get_decimal("sma_50"),
            ema_20=get_decimal("ema_20"),
            ema_50=get_decimal("ema_50"),
            distance_sma20_pct=get_decimal("distance_sma20_pct"),
            distance_sma50_pct=get_decimal("distance_sma50_pct"),
            rsi_14=get_decimal("rsi_14"),
            atr_14=get_decimal("atr_14"),
            atr_pct=get_decimal("atr_pct"),
            realized_vol_20=get_decimal("realized_vol_20"),
            avg_volume_20=get_decimal("avg_volume_20"),
            volume_ratio=get_decimal("volume_ratio"),
            volume_zscore=get_decimal("volume_zscore"),
            current_drawdown=get_decimal("current_drawdown"),
            trend_short=Trend(str(indicators.get("trend_short", Trend.UNKNOWN))),
            trend_medium=Trend(str(indicators.get("trend_medium", Trend.UNKNOWN))),
        )

    def _get_market_open(self) -> bool | None:
        """Check if market is currently open (if trading client available)."""
        try:
            # Check if gateway has trading client
            if hasattr(self._gateway, "_trading_client") and self._gateway._trading_client:
                clock = self._gateway._trading_client.get_clock()
                return bool(getattr(clock, "is_open", False))
        except Exception:
            pass
        return None