from __future__ import annotations

"""Tests for deterministic opportunity signals."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.discovery.models import ScreeningObservation, SignalDirection
from app.discovery.signals import (
    SignalWeights,
    compute_all_signals,
    compute_liquidity_signal,
    compute_mean_reversion_signal,
    compute_momentum_signal,
    compute_quality_signal,
    compute_trend_signal,
    compute_volatility_signal,
    compute_volume_signal,
)


class TestSignalWeights:
    def test_normalization(self) -> None:
        weights = SignalWeights(
            momentum=0.20,
            trend=0.20,
            volume=0.15,
            volatility=0.15,
            mean_reversion=0.10,
            liquidity=0.10,
            quality=0.10,
        )
        total = (
            weights.momentum + weights.trend + weights.volume +
            weights.volatility + weights.mean_reversion +
            weights.liquidity + weights.quality
        )
        assert abs(float(total) - 1.0) < 0.001

    def test_custom_weights_normalized(self) -> None:
        weights = SignalWeights(
            momentum=0.50,
            trend=0.50,
            volume=0.0,
            volatility=0.0,
            mean_reversion=0.0,
            liquidity=0.0,
            quality=0.0,
        )
        assert weights.momentum == 0.5
        assert weights.trend == 0.5
        assert weights.volume == 0.0

    def test_zero_total_raises(self) -> None:
        with pytest.raises(ValueError):
            SignalWeights(
                momentum=0.0,
                trend=0.0,
                volume=0.0,
                volatility=0.0,
                mean_reversion=0.0,
                liquidity=0.0,
                quality=0.0,
            )


class TestMomentumSignal:
    def test_strong_positive_5d(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("0.08"),  # 8% in 5 days
            return_20d=Decimal("0.10"),
        )
        score, direction, reasons = compute_momentum_signal(obs)
        assert direction == SignalDirection.BULLISH
        assert float(score) > 80
        assert any("STRONG_5D_MOMENTUM" in r for r in reasons)

    def test_negative_5d(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("-0.08"),
            return_20d=Decimal("-0.10"),
        )
        score, direction, reasons = compute_momentum_signal(obs)
        assert direction == SignalDirection.BEARISH
        assert float(score) < 30
        assert any("NEGATIVE_5D_MOMENTUM" in r for r in reasons)

    def test_flat_momentum(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("0.001"),
            return_20d=Decimal("0.002"),
        )
        score, direction, reasons = compute_momentum_signal(obs)
        assert direction == SignalDirection.NEUTRAL
        assert 45 <= float(score) <= 55


class TestTrendSignal:
    def test_strong_uptrend(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            distance_sma20_pct=Decimal("10.0"),
            distance_sma50_pct=Decimal("15.0"),
            trend_short="STRONG_UP",
            trend_medium="UP",
        )
        score, direction, reasons = compute_trend_signal(obs)
        assert direction == SignalDirection.BULLISH
        assert float(score) >= 80
        assert any("STRONG_UPTREND" in r for r in reasons)

    def test_strong_downtrend(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            distance_sma20_pct=Decimal("-10.0"),
            distance_sma50_pct=Decimal("-15.0"),
            trend_short="STRONG_DOWN",
            trend_medium="DOWN",
        )
        score, direction, reasons = compute_trend_signal(obs)
        assert direction == SignalDirection.BEARISH
        assert float(score) <= 20

    def test_mixed_trend(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            distance_sma20_pct=Decimal("5.0"),
            distance_sma50_pct=Decimal("-2.0"),
            trend_short="UP",
            trend_medium="DOWN",
        )
        score, direction, reasons = compute_trend_signal(obs)
        assert direction == SignalDirection.MIXED


class TestVolumeSignal:
    def test_unusual_volume(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            volume_ratio=Decimal("3.0"),
            volume_zscore=Decimal("2.5"),
        )
        score, direction, reasons = compute_volume_signal(obs)
        assert float(score) >= 80
        assert any("UNUSUAL_VOLUME" in r for r in reasons)

    def test_low_volume(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            volume_ratio=Decimal("0.3"),
        )
        score, direction, reasons = compute_volume_signal(obs)
        assert float(score) <= 40


class TestVolatilitySignal:
    def test_healthy_volatility(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            realized_vol_20=Decimal("0.25"),  # 25% annualized
        )
        score, direction, reasons = compute_volatility_signal(obs)
        assert float(score) >= 70
        assert any("HEALTHY_VOLATILITY" in r for r in reasons)

    def test_extreme_volatility_penalized(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            realized_vol_20=Decimal("0.80"),  # 80% annualized - extreme
        )
        score, direction, reasons = compute_volatility_signal(obs)
        assert float(score) <= 50
        assert any("EXTREME_VOLATILITY" in r for r in reasons)

    def test_very_low_volatility(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            realized_vol_20=Decimal("0.05"),  # 5% annualized
        )
        score, direction, reasons = compute_volatility_signal(obs)
        assert float(score) <= 40


class TestMeanReversionSignal:
    def test_rsi_oversold(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            rsi_14=Decimal("25"),
            distance_sma20_pct=Decimal("-1.0"),
            distance_sma50_pct=Decimal("5.0"),
        )
        score, direction, reasons = compute_mean_reversion_signal(obs)
        assert direction == SignalDirection.BULLISH
        assert float(score) >= 65
        assert any("RSI_OVERSOLD" in r for r in reasons)

    def test_rsi_overbought(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            rsi_14=Decimal("85"),
        )
        score, direction, reasons = compute_mean_reversion_signal(obs)
        assert direction == SignalDirection.BEARISH
        assert float(score) <= 40

    def test_pullback_in_uptrend(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            rsi_14=Decimal("50"),
            distance_sma20_pct=Decimal("-1.0"),
            distance_sma50_pct=Decimal("5.0"),
        )
        score, direction, reasons = compute_mean_reversion_signal(obs)
        assert direction == SignalDirection.BULLISH
        assert float(score) >= 60
        assert any("PULLBACK_IN_UPTREND" in r for r in reasons)


class TestLiquiditySignal:
    def test_high_liquidity(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            dollar_volume=Decimal("100_000_000"),
        )
        score, direction, reasons = compute_liquidity_signal(obs)
        assert float(score) >= 75
        assert any("HIGH_LIQUIDITY" in r for r in reasons)


class TestQualitySignal:
    def test_good_quality(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            data_quality_status="GOOD",
            bars_received=100,
        )
        score, direction, reasons = compute_quality_signal(obs)
        assert float(score) == 100
        assert any("DATA_QUALITY_GOOD" in r for r in reasons)

    def test_degraded_quality(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            data_quality_status="DEGRADED",
        )
        score, direction, reasons = compute_quality_signal(obs)
        assert float(score) == 70


class TestComputeAllSignals:
    def test_all_signals_computed(self) -> None:
        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("0.05"),
            return_20d=Decimal("0.10"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("2000000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("5.0"),
            distance_sma50_pct=Decimal("10.0"),
            rsi_14=Decimal("55"),
            trend_short="UP",
            trend_medium="UP",
            dollar_volume=Decimal("50_000_000"),
            data_quality_status="GOOD",
            bars_received=100,
        )
        signals = compute_all_signals(obs)

        expected_signals = [
            "momentum", "trend", "volume", "volatility",
            "mean_reversion", "liquidity", "quality"
        ]
        for s in expected_signals:
            assert s in signals
            score, direction, reasons = signals[s]
            assert isinstance(score, Decimal)
            assert isinstance(direction, SignalDirection)
            assert isinstance(reasons, list)