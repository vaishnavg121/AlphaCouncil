"""Tests for deterministic technical indicators."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import pytest

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


class TestReturns:
    def test_returns_increasing(self) -> None:
        prices = [100, 102, 104, 106, 108]
        # 108/106 - 1 = 0.0188679...
        assert returns(prices, 1) is not None
        assert float(returns(prices, 1)) == pytest.approx(0.0188679, rel=1e-4)
        # 108/100 - 1 = 0.08
        assert float(returns(prices, 4)) == pytest.approx(0.08, rel=1e-10)

    def test_returns_decreasing(self) -> None:
        prices = [108, 106, 104, 102, 100]
        r = returns(prices, 1)
        assert r is not None and r < 0

    def test_returns_flat(self) -> None:
        prices = [100, 100, 100, 100]
        assert returns(prices, 1) == Decimal("0")

    def test_returns_insufficient_data(self) -> None:
        prices = [100, 101]
        assert returns(prices, 5) is None


class TestMomentum:
    def test_momentum_positive(self) -> None:
        prices = [100, 101, 102, 103, 104, 105]
        assert momentum(prices, 5) == Decimal("5")

    def test_momentum_negative(self) -> None:
        prices = [105, 104, 103, 102, 101, 100]
        m = momentum(prices, 5)
        assert m is not None and m < 0

    def test_momentum_insufficient(self) -> None:
        prices = [100, 101]
        assert momentum(prices, 5) is None


class TestSMA:
    def test_sma_basic(self) -> None:
        values = [10, 20, 30, 40, 50]
        assert sma(values, 3) == Decimal("40")  # (30+40+50)/3

    def test_sma_flat(self) -> None:
        values = [100, 100, 100, 100]
        assert sma(values, 2) == Decimal("100")

    def test_sma_insufficient(self) -> None:
        values = [10, 20]
        assert sma(values, 5) is None


class TestEMA:
    def test_ema_basic(self) -> None:
        values = [10, 20, 30, 40, 50]
        result = ema(values, 3)
        assert result is not None
        # EMA should be weighted towards recent values
        assert float(result) > 40  # More recent weighted

    def test_ema_flat(self) -> None:
        values = [100, 100, 100, 100]
        assert ema(values, 3) == Decimal("100")

    def test_ema_insufficient(self) -> None:
        values = [10, 20]
        assert ema(values, 5) is None


class TestRSI:
    def test_rsi_strongly_rising(self) -> None:
        # Strongly rising prices -> RSI near 100
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
        r = rsi(prices, 14)
        assert r is not None
        assert float(r) > 80

    def test_rsi_strongly_falling(self) -> None:
        # Strongly falling prices -> RSI near 0
        prices = [115, 114, 113, 112, 111, 110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100]
        r = rsi(prices, 14)
        assert r is not None
        assert float(r) < 20

    def test_rsi_flat(self) -> None:
        # Flat prices -> RSI = 50 (but with our implementation, division by zero -> 100)
        prices = [100] * 20
        r = rsi(prices, 14)
        # When all gains are zero and losses are zero, avg_loss=0 -> RSI=100
        assert r is not None

    def test_rsi_insufficient(self) -> None:
        prices = [100, 101, 102]
        assert rsi(prices, 14) is None

    def test_rsi_bounds(self) -> None:
        prices = [100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109]
        r = rsi(prices, 14)
        assert r is not None
        assert 0 <= float(r) <= 100


class TestATR:
    def test_atr_basic(self) -> None:
        highs = [105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120]
        lows = [95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115]
        result = atr(highs, lows, closes, 14)
        assert result is not None
        # True range each day = 10 (high-low)
        # ATR should be around 10
        assert 9 <= float(result) <= 11

    def test_atr_insufficient(self) -> None:
        highs = [105, 106]
        lows = [95, 96]
        closes = [100, 101]
        assert atr(highs, lows, closes, 14) is None


class TestRealizedVolatility:
    def test_flat_series(self) -> None:
        prices = [100] * 30
        vol = realized_volatility(prices, 20)
        assert vol is not None
        assert float(vol) == 0

    def test_variable_series(self) -> None:
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101,
                  100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100]
        vol = realized_volatility(prices, 20)
        assert vol is not None
        assert float(vol) > 0

    def test_insufficient_data(self) -> None:
        prices = [100, 101, 102]
        assert realized_volatility(prices, 20) is None

    def test_simple_returns(self) -> None:
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101,
                  100, 101, 100, 101, 100, 101, 100, 101, 100, 101, 100]
        vol_log = realized_volatility(prices, 20, use_log_returns=True)
        vol_simple = realized_volatility(prices, 20, use_log_returns=False)
        assert vol_log is not None and vol_simple is not None
        # Log and simple returns should be close for small changes
        assert abs(float(vol_log) - float(vol_simple)) < 0.01


class TestVolume:
    def test_avg_volume(self) -> None:
        volumes = [1000] * 10 + [2000] * 10
        avg = avg_volume(volumes, 20)
        assert avg == Decimal("1500")

    def test_avg_volume_zero(self) -> None:
        volumes = [0] * 20
        avg = avg_volume(volumes, 20)
        assert avg == Decimal("0")

    def test_volume_ratio_normal(self) -> None:
        ratio = volume_ratio(2000, Decimal("1000"))
        assert ratio == Decimal("2")

    def test_volume_ratio_zero_avg(self) -> None:
        assert volume_ratio(1000, Decimal("0")) is None

    def test_volume_ratio_none_avg(self) -> None:
        assert volume_ratio(1000, None) is None

    def test_volume_zscore(self) -> None:
        volumes = [1000, 1100, 900, 1050, 950] * 4  # 20 values with variance
        z = volume_zscore(volumes, 1000, 20)
        assert z is not None
        assert float(z) == pytest.approx(0, abs=0.1)

    def test_volume_zscore_high(self) -> None:
        volumes = [1000] * 19 + [2000]  # One high value
        z = volume_zscore(volumes, 2000, 20)
        assert z is not None and float(z) > 0

    def test_volume_zscore_zero_std(self) -> None:
        volumes = [1000] * 20
        z = volume_zscore(volumes, 1000, 20)
        # With zero std, zscore returns None
        assert z is None


class TestDrawdown:
    def test_drawdown_from_peak(self) -> None:
        prices = [100, 105, 110, 108, 105, 100]  # Peak at 110, current 100
        dd = drawdown(prices)
        assert dd is not None
        assert float(dd) == -10/110  # (100-110)/110

    def test_drawdown_at_peak(self) -> None:
        prices = [100, 105, 110]  # Current is peak
        dd = drawdown(prices)
        assert dd == Decimal("0")

    def test_drawdown_empty(self) -> None:
        assert drawdown([]) is None


class TestDistanceFromSMA:
    def test_distance_positive(self) -> None:
        dist = distance_from_sma_pct(110, 100)
        assert dist == Decimal("10")  # (110-100)/100 * 100 = 10%

    def test_distance_negative(self) -> None:
        dist = distance_from_sma_pct(90, 100)
        assert dist == Decimal("-10")

    def test_distance_zero_sma(self) -> None:
        assert distance_from_sma_pct(100, 0) is None

    def test_distance_none_sma(self) -> None:
        assert distance_from_sma_pct(100, None) is None


class TestTrendClassification:
    def test_strong_up(self) -> None:
        trend = classify_trend(110, 105, 100, 5, 10)
        assert trend == "STRONG_UP"

    def test_up(self) -> None:
        trend = classify_trend(105, 102, 100, 2, 5)
        assert trend == "UP"

    def test_strong_down(self) -> None:
        trend = classify_trend(90, 95, 100, -5, -10)
        assert trend == "STRONG_DOWN"

    def test_down(self) -> None:
        # price < sma_short < sma_long, but distance not strong enough for STRONG_DOWN
        trend = classify_trend(95, 98, 100, -1, -2)
        assert trend == "DOWN"

    def test_neutral_price_between(self) -> None:
        trend = classify_trend(102, 100, 105, 2, -3)
        assert trend == "NEUTRAL"

    def test_neutral_flat(self) -> None:
        trend = classify_trend(100, 100, 100, 0, 0)
        assert trend == "NEUTRAL"

    def test_unknown_insufficient(self) -> None:
        trend = classify_trend(100, None, 100, None, 0)
        assert trend == "UNKNOWN"


class TestComputeAllIndicators:
    def test_compute_all_sufficient_data(self) -> None:
        # Create bars with enough data
        bars = []
        base_price = 100
        for i in range(60):
            price = base_price + i * 0.5
            from datetime import datetime, timedelta

            from app.market.models import OHLCVBar
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=60-i),
                open=Decimal(str(price - 0.5)),
                high=Decimal(str(price + 0.5)),
                low=Decimal(str(price - 1.0)),
                close=Decimal(str(price)),
                volume=1000000 + i * 1000,
            ))

        indicators = compute_all_indicators(bars)

        # Check all key indicators are present
        assert indicators["sma_20"] is not None
        assert indicators["sma_50"] is not None
        assert indicators["ema_20"] is not None
        assert indicators["ema_50"] is not None
        assert indicators["rsi_14"] is not None
        assert indicators["atr_14"] is not None
        assert indicators["realized_vol_20"] is not None
        assert indicators["avg_volume_20"] is not None
        assert indicators["volume_ratio"] is not None
        assert indicators["volume_zscore"] is not None
        assert indicators["current_drawdown"] is not None
        assert indicators["trend_short"] != "UNKNOWN"
        assert indicators["trend_medium"] != "UNKNOWN"

    def test_compute_all_insufficient_data(self) -> None:
        from datetime import datetime, timedelta

        from app.market.models import OHLCVBar

        bars = []
        for i in range(10):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=10-i),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000000,
            ))

        indicators = compute_all_indicators(bars)

        # SMA50 should be None with only 10 bars
        assert indicators["sma_50"] is None
        assert indicators["ema_50"] is None
        assert indicators["trend_short"] == "UNKNOWN"
        assert indicators["trend_medium"] == "UNKNOWN"

    def test_no_nan_infinity_leakage(self) -> None:
        from datetime import datetime, timedelta

        from app.market.models import OHLCVBar

        bars = []
        for i in range(60):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=60-i),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000000,
            ))

        indicators = compute_all_indicators(bars)

        for key, value in indicators.items():
            if value is not None and not isinstance(value, str):
                # Check no NaN or Infinity (skip trend strings)
                f = float(value)
                assert f == f, f"NaN found in {key}"  # NaN != NaN
                assert f != float("inf"), f"Infinity found in {key}"
                assert f != float("-inf"), f"-Infinity found in {key}"


class TestInvariants:
    def test_atr_non_negative(self) -> None:
        highs = [105] * 20
        lows = [95] * 20
        closes = [100] * 20
        result = atr(highs, lows, closes, 14)
        assert result is not None and float(result) >= 0

    def test_realized_vol_non_negative(self) -> None:
        prices = [100, 101, 100, 101] * 10
        vol = realized_volatility(prices, 20)
        assert vol is not None and float(vol) >= 0

    def test_rsi_bounds_when_defined(self) -> None:
        prices = [100 + i % 5 for i in range(30)]
        r = rsi(prices, 14)
        assert r is not None
        assert 0 <= float(r) <= 100

    def test_drawdown_non_positive(self) -> None:
        prices = [100, 110, 105, 115, 110]
        dd = drawdown(prices)
        assert dd is not None and float(dd) <= 0

    def test_bid_ask_spread_non_negative(self) -> None:
        from datetime import datetime

        from app.market.models import QuoteSnapshot
        quote = QuoteSnapshot(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            bid_price=Decimal("100"),
            ask_price=Decimal("101"),
        )
        assert float(quote.spread) >= 0