"""Deterministic opportunity signals for M2 discovery.

Signal components are computed from ScreeningObservation and produce
normalized 0-100 scores with explainability.
"""

from __future__ import annotations

from decimal import Decimal

from app.discovery.models import (
    ScreeningObservation,
    SignalDirection,
)


class SignalWeights:
    """Centralized signal weights (normalized to sum=1.0)."""

    def __init__(
        self,
        momentum: float = 0.20,
        trend: float = 0.20,
        volume: float = 0.15,
        volatility: float = 0.15,
        mean_reversion: float = 0.10,
        liquidity: float = 0.10,
        quality: float = 0.10,
    ) -> None:
        self.momentum = momentum
        self.trend = trend
        self.volume = volume
        self.volatility = volatility
        self.mean_reversion = mean_reversion
        self.liquidity = liquidity
        self.quality = quality

        total = (
            momentum + trend + volume + volatility +
            mean_reversion + liquidity + quality
        )
        if total <= 0:
            raise ValueError("At least one weight must be positive")

        # Normalize
        self.momentum = momentum / total
        self.trend = trend / total
        self.volume = volume / total
        self.volatility = volatility / total
        self.mean_reversion = mean_reversion / total
        self.liquidity = liquidity / total
        self.quality = quality / total


def compute_momentum_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute momentum signal from returns.

    Returns: (score_0_100, direction, reasons)
    """
    reasons = []
    score = Decimal("50")  # Neutral baseline
    direction = SignalDirection.NEUTRAL

    if obs.return_5d is not None and obs.return_20d is not None:
        r5 = float(obs.return_5d)
        r20 = float(obs.return_20d)

        # 5d momentum (more weight for recent)
        if r5 > 0.05:  # >5% in 5 days
            score = Decimal(str(min(100, 50 + r5 * 500)))
            direction = SignalDirection.BULLISH
            reasons.append(f"STRONG_5D_MOMENTUM ({r5:.1%})")
        elif r5 > 0.02:
            score = Decimal(str(min(100, 50 + r5 * 1000)))
            direction = SignalDirection.BULLISH
            reasons.append(f"POSITIVE_5D_MOMENTUM ({r5:.1%})")
        elif r5 < -0.05:
            score = Decimal(str(max(0, 50 + r5 * 500)))
            direction = SignalDirection.BEARISH
            reasons.append(f"STRONG_NEGATIVE_5D_MOMENTUM ({r5:.1%})")
        elif r5 < -0.02:
            score = Decimal(str(max(0, 50 + r5 * 1000)))
            direction = SignalDirection.BEARISH
            reasons.append(f"NEGATIVE_5D_MOMENTUM ({r5:.1%})")

        # 20d momentum adds confirmation
        if r20 > 0.10:
            score = min(score, Decimal("100")) + Decimal("10")
            if direction == SignalDirection.BULLISH:
                reasons.append(f"POSITIVE_20D_MOMENTUM ({r20:.1%})")
        elif r20 < -0.10:
            score = max(score, Decimal("0")) - Decimal("10")
            if direction == SignalDirection.BEARISH:
                reasons.append(f"NEGATIVE_20D_MOMENTUM ({r20:.1%})")

    return score, direction, reasons


def compute_trend_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute trend signal from SMA distances and trend classification."""
    reasons = []
    score = Decimal("50")
    direction = SignalDirection.NEUTRAL

    if obs.distance_sma20_pct is not None and obs.distance_sma50_pct is not None:
        d20 = float(obs.distance_sma20_pct)
        d50 = float(obs.distance_sma50_pct)

        # Price above both SMAs = uptrend
        if d20 > 0 and d50 > 0:
            if d20 > 5 and d50 > 5:
                score = Decimal("90")
                direction = SignalDirection.BULLISH
                reasons.append(f"STRONG_UPTREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")
            else:
                score = Decimal("70")
                direction = SignalDirection.BULLISH
                reasons.append(f"UPTREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")
        # Price below both SMAs = downtrend
        elif d20 < 0 and d50 < 0:
            if d20 < -5 and d50 < -5:
                score = Decimal("10")
                direction = SignalDirection.BEARISH
                reasons.append(f"STRONG_DOWNTREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")
            else:
                score = Decimal("30")
                direction = SignalDirection.BEARISH
                reasons.append(f"DOWNTREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")
        else:
            # Mixed - price between SMAs
            score = Decimal("50")
            direction = SignalDirection.MIXED
            reasons.append(f"MIXED_TREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")

    # Trend classification confirmation
    if obs.trend_short and obs.trend_medium:
        if "UP" in obs.trend_short and "UP" in obs.trend_medium:
            if direction != SignalDirection.BEARISH:
                direction = SignalDirection.BULLISH
            score = min(score + Decimal("10"), Decimal("100"))
            reasons.append(f"TREND_ALIGNED ({obs.trend_short}/{obs.trend_medium})")
        elif "DOWN" in obs.trend_short and "DOWN" in obs.trend_medium:
            if direction != SignalDirection.BULLISH:
                direction = SignalDirection.BEARISH
            score = max(score - Decimal("10"), Decimal("0"))
            reasons.append(f"TREND_ALIGNED_DOWN ({obs.trend_short}/{obs.trend_medium})")

    return score, direction, reasons


def compute_volume_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute volume signal from volume ratio and z-score."""
    reasons = []
    score = Decimal("50")
    direction = SignalDirection.NEUTRAL

    if obs.volume_ratio is not None:
        vr = float(obs.volume_ratio)
        if vr >= 2.0:
            score = Decimal("85")
            direction = SignalDirection.BULLISH if (obs.return_1d or Decimal("0")) > 0 else SignalDirection.MIXED
            reasons.append(f"UNUSUAL_VOLUME ({vr:.1f}x avg)")
        elif vr >= 1.5:
            score = Decimal("70")
            reasons.append(f"ELEVATED_VOLUME ({vr:.1f}x avg)")
        elif vr <= 0.5:
            score = Decimal("30")
            reasons.append(f"LOW_VOLUME ({vr:.1f}x avg)")

    if obs.volume_zscore is not None:
        vz = float(obs.volume_zscore)
        if vz >= 2.0:
            score = max(score, Decimal("80"))
            reasons.append(f"VOLUME_ZSCORE_HIGH ({vz:.1f})")
        elif vz <= -2.0:
            score = min(score, Decimal("20"))
            reasons.append(f"VOLUME_ZSCORE_LOW ({vz:.1f})")

    return score, direction, reasons


def compute_volatility_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute volatility signal - reward moderate movement, penalize extremes."""
    reasons = []
    score = Decimal("50")
    direction = SignalDirection.NEUTRAL

    if obs.realized_vol_20 is not None:
        vol = float(obs.realized_vol_20)
        # Target band: 15-40% annualized vol
        if 0.15 <= vol <= 0.40:
            score = Decimal("75")
            reasons.append(f"HEALTHY_VOLATILITY ({vol:.1%})")
        elif 0.10 <= vol < 0.15:
            score = Decimal("60")
            reasons.append(f"LOW_VOLATILITY ({vol:.1%})")
        elif 0.40 < vol <= 0.60:
            score = Decimal("60")
            reasons.append(f"ELEVATED_VOLATILITY ({vol:.1%})")
        elif vol > 0.60:
            # Penalize extreme volatility - chaotic, not necessarily opportunity
            score = Decimal("40")
            reasons.append(f"EXTREME_VOLATILITY ({vol:.1%})")
        elif vol < 0.10:
            score = Decimal("30")
            reasons.append(f"VERY_LOW_VOLATILITY ({vol:.1%})")

    if obs.atr_pct is not None:
        atrp = float(obs.atr_pct)
        # ATR% as additional context
        if atrp > 5.0:
            reasons.append(f"HIGH_ATR_PCT ({atrp:.1f}%)")
        elif atrp < 1.0:
            reasons.append(f"LOW_ATR_PCT ({atrp:.1f}%)")

    return score, direction, reasons


def compute_mean_reversion_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute mean reversion / pullback signal from RSI and SMA distance."""
    reasons = []
    score = Decimal("50")
    direction = SignalDirection.NEUTRAL

    if obs.rsi_14 is not None:
        rsi = float(obs.rsi_14)
        if rsi <= 30:
            # Oversold - potential bounce candidate (bullish for mean reversion)
            score = Decimal("70")
            direction = SignalDirection.BULLISH
            reasons.append(f"RSI_OVERSOLD ({rsi:.0f})")
        elif rsi <= 40:
            score = Decimal("60")
            direction = SignalDirection.BULLISH
            reasons.append(f"RSI_LOW ({rsi:.0f})")
        elif rsi >= 70:
            # Overbought - potential pullback (bearish for mean reversion)
            score = Decimal("30")
            direction = SignalDirection.BEARISH
            reasons.append(f"RSI_OVERBOUGHT ({rsi:.0f})")
        elif rsi >= 60:
            score = Decimal("40")
            direction = SignalDirection.BEARISH
            reasons.append(f"RSI_HIGH ({rsi:.0f})")

    # Pullback in uptrend: price near SMA20 but SMA20 > SMA50
    if obs.distance_sma20_pct is not None and obs.distance_sma50_pct is not None:
        d20 = float(obs.distance_sma20_pct)
        d50 = float(obs.distance_sma50_pct)
        # Pullback: price near/below SMA20 but SMA20 still above SMA50
        if -3 <= d20 <= 1 and d50 > 2:
            score = max(score, Decimal("65"))
            direction = SignalDirection.BULLISH
            reasons.append(f"PULLBACK_IN_UPTREND (SMA20:{d20:.1f}%, SMA50:{d50:.1f}%)")

    return score, direction, reasons


def compute_liquidity_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute liquidity signal from dollar volume."""
    reasons = []
    score = Decimal("50")
    direction = SignalDirection.NEUTRAL

    if obs.dollar_volume is not None:
        dv = float(obs.dollar_volume)
        # Log scale: $1M=0, $10M=50, $100M=100
        import math
        if dv > 0:
            log_dv = math.log10(dv)
            score = Decimal(str(min(100, max(0, (log_dv - 6) * 50))))
            if dv >= 50_000_000:
                reasons.append(f"HIGH_LIQUIDITY (${dv/1e6:.0f}M)")
            elif dv >= 10_000_000:
                reasons.append(f"GOOD_LIQUIDITY (${dv/1e6:.0f}M)")
            else:
                reasons.append(f"MODERATE_LIQUIDITY (${dv/1e6:.0f}M)")

    return score, direction, reasons


def compute_quality_signal(obs: ScreeningObservation) -> tuple[Decimal, SignalDirection, list[str]]:
    """Compute data quality signal."""
    reasons = []
    score = Decimal("100")
    direction = SignalDirection.NEUTRAL

    if obs.data_quality_status == "GOOD":
        score = Decimal("100")
        reasons.append("DATA_QUALITY_GOOD")
    elif obs.data_quality_status == "DEGRADED":
        score = Decimal("70")
        reasons.append("DATA_QUALITY_DEGRADED")
    elif obs.data_quality_status == "INSUFFICIENT":
        score = Decimal("30")
        reasons.append("DATA_QUALITY_INSUFFICIENT")
    elif obs.data_quality_status == "STALE":
        score = Decimal("20")
        reasons.append("DATA_STALE")

    # Bars received vs expected
    if obs.bars_received is not None:
        if obs.bars_received >= 100:
            reasons.append(f"SUFFICIENT_HISTORY ({obs.bars_received} bars)")
        elif obs.bars_received >= 50:
            score = min(score, Decimal("80"))
            reasons.append(f"ADEQUATE_HISTORY ({obs.bars_received} bars)")

    return score, direction, reasons


def compute_all_signals(
    obs: ScreeningObservation,
    weights: SignalWeights | None = None,
) -> dict[str, tuple[Decimal, SignalDirection, list[str]]]:
    """Compute all signal components for an observation.

    Returns dict of signal_name -> (score, direction, reasons)
    """
    return {
        "momentum": compute_momentum_signal(obs),
        "trend": compute_trend_signal(obs),
        "volume": compute_volume_signal(obs),
        "volatility": compute_volatility_signal(obs),
        "mean_reversion": compute_mean_reversion_signal(obs),
        "liquidity": compute_liquidity_signal(obs),
        "quality": compute_quality_signal(obs),
    }