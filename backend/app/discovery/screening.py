"""Bulk screening data retrieval for M2 discovery.

Efficiently retrieves screening data for multiple symbols using
batch requests where possible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.config import Settings
from app.discovery.models import ScreeningObservation
from app.market.gateway import MarketDataError, MarketDataGateway
from app.market.models import MarketSnapshot
from app.market.indicators import (
    atr,
    avg_volume,
    classify_trend,
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
from app.market.models import DataQualityStatus, OHLCVBar, Timeframe


class BulkScreener:
    """Retrieve and compute screening observations for multiple symbols."""

    def __init__(
        self,
        gateway: MarketDataGateway,
        settings: Settings | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings or Settings()
        self._lookback_days = 150  # Same as M1 default

    def screen_symbols(
        self,
        symbols: list[str],
        timeframe: Timeframe = Timeframe.DAY,
    ) -> list[ScreeningObservation]:
        """Screen multiple symbols and return observations.

        Args:
            symbols: List of symbols to screen.
            timeframe: Bar timeframe for analysis.

        Returns:
            List of ScreeningObservation (one per symbol, may have errors).
        """
        observations = []

        for symbol in symbols:
            try:
                obs = self._screen_single(symbol, timeframe)
                observations.append(obs)
            except MarketDataError:
                # Create minimal observation with error info
                observations.append(
                    ScreeningObservation(
                        symbol=symbol,
                        as_of=datetime.now(UTC),
                        price=Decimal("0"),
                        data_quality_status="PROVIDER_ERROR",
                    )
                )
            except Exception:
                observations.append(
                    ScreeningObservation(
                        symbol=symbol,
                        as_of=datetime.now(UTC),
                        price=Decimal("0"),
                        data_quality_status="INVALID_DATA",
                    )
                )

        return observations

    def _screen_single(
        self,
        symbol: str,
        timeframe: Timeframe,
    ) -> ScreeningObservation:
        """Screen a single symbol."""
        # Get bars for indicator computation
        end = datetime.now(UTC)
        start = end - timedelta(days=self._lookback_days)

        bars = self._gateway.get_bars(symbol, timeframe, start, end)

        if not bars:
            return ScreeningObservation(
                symbol=symbol,
                as_of=datetime.now(UTC),
                price=Decimal("0"),
                data_quality_status="INSUFFICIENT",
                bars_received=0,
            )

        # Validate bars (similar to M1)
        bars, data_quality_status = self._validate_bars(bars, symbol)

        if len(bars) < 20:  # Minimum for basic screening
            return ScreeningObservation(
                symbol=symbol,
                as_of=datetime.now(UTC),
                price=Decimal(str(bars[-1].close)) if bars else Decimal("0"),
                data_quality_status=str(data_quality_status),
                bars_received=len(bars),
            )

        # Get snapshot for current price and volume
        snapshot = self._gateway.get_snapshot(symbol)

        # Extract price series
        closes = [float(b.close) for b in bars]
        highs = [float(b.high) for b in bars]
        lows = [float(b.low) for b in bars]
        volumes = [float(b.volume) for b in bars]

        # Current price
        current_price = self._get_current_price(snapshot, bars[-1] if bars else None)

        # Compute all indicators
        ret_1d = returns(closes, 1)
        ret_5d = returns(closes, 5)
        ret_20d = returns(closes, 20)

        mom_5d = momentum(closes, 5)
        mom_20d = momentum(closes, 20)

        sma_20 = sma(closes, 20)
        sma_50 = sma(closes, 50)
        ema_20 = ema(closes, 20)
        ema_50 = ema(closes, 50)

        dist_sma20 = distance_from_sma_pct(current_price, sma_20)
        dist_sma50 = distance_from_sma_pct(current_price, sma_50)

        rsi_14 = rsi(closes, 14)

        atr_14 = atr(highs, lows, closes, 14)
        atr_pct = None
        if atr_14 is not None and current_price != 0:
            atr_pct = Decimal(str((float(atr_14) / float(current_price)) * 100))

        realized_vol_20 = realized_volatility(closes, 20)

        avg_vol_20 = avg_volume(volumes, 20)
        vol_ratio = volume_ratio(volumes[-1] if volumes else 0, avg_vol_20)
        vol_zscore = volume_zscore(volumes, volumes[-1] if volumes else 0, 20)

        cur_drawdown = drawdown(closes)

        trend_short = classify_trend(current_price, sma_20, sma_50, dist_sma20, dist_sma50)
        trend_medium = classify_trend(current_price, sma_50, sma_20, dist_sma50, dist_sma20)

        # Dollar volume
        dollar_volume = None
        if avg_vol_20 is not None and current_price != 0:
            dollar_volume = Decimal(str(float(avg_vol_20) * float(current_price)))

        return ScreeningObservation(
            symbol=symbol,
            as_of=datetime.now(UTC),
            price=current_price,
            return_1d=ret_1d,
            return_5d=ret_5d,
            return_20d=ret_20d,
            volume=Decimal(str(volumes[-1])) if volumes else None,
            avg_volume_20=avg_vol_20,
            volume_ratio=vol_ratio,
            volume_zscore=vol_zscore,
            realized_vol_20=realized_vol_20,
            atr_pct=atr_pct,
            distance_sma20_pct=dist_sma20,
            distance_sma50_pct=dist_sma50,
            rsi_14=rsi_14,
            trend_short=trend_short,
            trend_medium=trend_medium,
            dollar_volume=dollar_volume,
            data_quality_status=str(data_quality_status),
            bars_received=len(bars),
        )

    def _validate_bars(
        self,
        bars: list[OHLCVBar],
        symbol: str,
    ) -> tuple[list[OHLCVBar], DataQualityStatus]:
        """Validate bars (simplified version of M1 validation)."""
        seen_timestamps = set()
        unique_bars = []
        duplicate_bars = 0
        missing_values = 0

        for bar in bars:
            ts = bar.timestamp
            if ts in seen_timestamps:
                duplicate_bars += 1
            else:
                seen_timestamps.add(ts)
                unique_bars.append(bar)

        for bar in unique_bars:
            if not bar.validate_ohlc():
                missing_values += 1

        if missing_values > len(unique_bars) * 0.1:
            status = DataQualityStatus.DEGRADED
        elif len(unique_bars) < 20:
            status = DataQualityStatus.INSUFFICIENT
        elif duplicate_bars > 0 or missing_values > 0:
            status = DataQualityStatus.DEGRADED
        else:
            status = DataQualityStatus.GOOD

        return unique_bars, status

    def _get_current_price(
        self,
        snapshot: MarketSnapshot,
        latest_bar: OHLCVBar | None,
    ) -> Decimal:
        """Get best available current price."""
        if snapshot.trade is not None:
            return snapshot.trade.price
        if snapshot.quote is not None and snapshot.quote.is_valid():
            return snapshot.quote.midpoint
        if latest_bar is not None:
            return latest_bar.close
        return Decimal("0")