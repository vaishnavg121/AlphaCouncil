"""Deterministic technical indicator calculations.

All indicators are computed using pure Python/NumPy with no external dependencies.
No LLM calls are made during indicator computation.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from math import sqrt
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.market.models import OHLCVBar


def to_decimal(value: float | int | None) -> Decimal | None:
    """Convert a float to Decimal, handling None and NaN."""
    if value is None:
        return None
    if isinstance(value, float) and (value != value or value == float("inf") or value == float("-inf")):
        return None
    return Decimal(str(value))


def to_float_array(values: Sequence[Decimal | float | int]) -> np.ndarray:
    """Convert a sequence of Decimal/float/int to a NumPy float64 array."""
    return np.array([float(v) for v in values], dtype=np.float64)


def returns(prices: Sequence[Decimal | float | int], period: int = 1) -> Decimal | None:
    """Calculate period return: (price[-1] / price[-(period+1)]) - 1.

    Args:
        prices: Sequence of closing prices (chronological order).
        period: Number of periods to look back.

    Returns:
        Decimal return or None if insufficient data.
    """
    arr = to_float_array(prices)
    if len(arr) < period + 1:
        return None
    if arr[-(period + 1)] == 0:
        return None
    return to_decimal((arr[-1] / arr[-(period + 1)]) - 1)


def momentum(prices: Sequence[Decimal | float | int], period: int = 5) -> Decimal | None:
    """Calculate momentum: current_price - price_n_periods_ago.

    Args:
        prices: List of closing prices (chronological order).
        period: Number of periods to look back.

    Returns:
        Decimal momentum or None if insufficient data.
    """
    arr = to_float_array(prices)
    if len(arr) < period + 1:
        return None
    return to_decimal(arr[-1] - arr[-(period + 1)])


def sma(values: Sequence[Decimal | float | int], period: int) -> Decimal | None:
    """Simple Moving Average.

    Args:
        values: Sequence of values (chronological order).
        period: SMA period.

    Returns:
        Decimal SMA or None if insufficient data.
    """
    arr = to_float_array(values)
    if len(arr) < period:
        return None
    return to_decimal(np.mean(arr[-period:]))


def ema(values: Sequence[Decimal | float | int], period: int) -> Decimal | None:
    """Exponential Moving Average using standard Wilder's smoothing.

    Args:
        values: Sequence of values (chronological order).
        period: EMA period.

    Returns:
        Decimal EMA or None if insufficient data.
    """
    arr = to_float_array(values)
    if len(arr) < period:
        return None

    alpha = 2.0 / (period + 1.0)
    ema_val = arr[0]
    for price in arr[1:]:
        ema_val = alpha * price + (1.0 - alpha) * ema_val
    return to_decimal(ema_val)


def rsi(prices: Sequence[Decimal | float | int], period: int = 14) -> Decimal | None:
    """Relative Strength Index (RSI) using Wilder's smoothing.

    Args:
        prices: Sequence of closing prices (chronological order).
        period: RSI period (default 14).

    Returns:
        Decimal RSI (0-100) or None if insufficient data.
    """
    arr = to_float_array(prices)
    if len(arr) < period + 1:
        return None

    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        return Decimal("100")

    rs = avg_gain / avg_loss
    rsi_val = 100.0 - (100.0 / (1.0 + rs))
    return to_decimal(rsi_val)


def atr(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    period: int = 14,
) -> Decimal | None:
    """Average True Range (ATR) using Wilder's smoothing.

    True Range = max(high - low, |high - prev_close|, |low - prev_close|)

    Args:
        highs: Sequence of high prices.
        lows: Sequence of low prices.
        closes: Sequence of close prices.
        period: ATR period (default 14).

    Returns:
        Decimal ATR or None if insufficient data.
    """
    highs_arr = to_float_array(highs)
    lows_arr = to_float_array(lows)
    closes_arr = to_float_array(closes)

    if len(highs_arr) < period + 1 or len(lows_arr) < period + 1 or len(closes_arr) < period + 1:
        return None

    true_ranges = []
    for i in range(1, len(highs_arr)):
        tr = max(
            highs_arr[i] - lows_arr[i],
            abs(highs_arr[i] - closes_arr[i - 1]),
            abs(lows_arr[i] - closes_arr[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    atr_val = np.mean(true_ranges[:period])
    for tr in true_ranges[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period

    return to_decimal(atr_val)


def realized_volatility(
    prices: Sequence[Decimal | float | int],
    period: int = 20,
    annualize: bool = True,
    trading_days: int = 252,
    use_log_returns: bool = True,
) -> Decimal | None:
    """Realized volatility (standard deviation of returns).

    Args:
        prices: Sequence of closing prices (chronological order).
        period: Lookback period for volatility calculation.
        annualize: Whether to annualize the volatility.
        trading_days: Number of trading days per year for annualization.
        use_log_returns: Use log returns (True) or simple returns (False).

    Returns:
        Decimal realized volatility or None if insufficient data.
    """
    arr = to_float_array(prices)
    if len(arr) < period + 1:
        return None

    if use_log_returns:
        returns_arr = np.diff(np.log(arr[-period - 1 :]))
    else:
        returns_arr = np.diff(arr[-period - 1 :]) / arr[-period - 1 : -1]

    if len(returns_arr) < 2:
        return None

    vol = np.std(returns_arr, ddof=1)
    if annualize:
        vol *= sqrt(trading_days)
    return to_decimal(vol)


def avg_volume(volumes: Sequence[Decimal | float | int], period: int = 20) -> Decimal | None:
    """Average volume over a period."""
    return sma(volumes, period)


def volume_ratio(current_volume: int | float | Decimal, avg_vol: Decimal | float | int | None) -> Decimal | None:
    """Current volume / average volume ratio."""
    if avg_vol is None:
        return None
    avg_f = float(avg_vol)
    if avg_f == 0:
        return None
    return to_decimal(float(current_volume) / avg_f)


def volume_zscore(
    volumes: Sequence[Decimal | float | int],
    current_volume: int | float | Decimal,
    period: int = 20,
) -> Decimal | None:
    """Z-score of current volume relative to rolling window."""
    arr = to_float_array(volumes)
    if len(arr) < period:
        return None

    window = arr[-period:]
    mean_vol = np.mean(window)
    std_vol = np.std(window, ddof=1)

    if std_vol == 0:
        return None

    z = (float(current_volume) - mean_vol) / std_vol
    return to_decimal(z)


def drawdown(prices: Sequence[Decimal | float | int]) -> Decimal | None:
    """Current drawdown from running peak.

    Returns a negative value (or zero) representing the percentage decline
    from the highest price seen so far.
    """
    arr = to_float_array(prices)
    if len(arr) == 0:
        return None

    peak = np.maximum.accumulate(arr)
    current = arr[-1]
    if peak[-1] == 0:
        return None
    dd = (current - peak[-1]) / peak[-1]
    return to_decimal(dd)


def distance_from_sma_pct(current_price: Decimal | float | int, sma_val: Decimal | float | int | None) -> Decimal | None:
    """Percentage distance from SMA: (price - sma) / sma * 100."""
    if sma_val is None:
        return None
    sma_f = float(sma_val)
    if sma_f == 0:
        return None
    return to_decimal(((float(current_price) - sma_f) / sma_f) * 100)


def classify_trend(
    price: Decimal | float | int,
    sma_short: Decimal | float | int | None,
    sma_long: Decimal | float | int | None,
    distance_short_pct: Decimal | float | int | None,
    distance_long_pct: Decimal | float | int | None,
) -> str:
    """Classify trend based on price vs moving averages.

    Rules:
    - STRONG_UP: price > SMA_short > SMA_long, both distances > 2%
    - UP: price > SMA_short > SMA_long
    - NEUTRAL: price between SMAs or SMAs flat
    - DOWN: price < SMA_short < SMA_long
    - STRONG_DOWN: price < SMA_short < SMA_long, both distances < -2%
    - UNKNOWN: insufficient data
    """
    if sma_short is None or sma_long is None or distance_short_pct is None or distance_long_pct is None:
        return "UNKNOWN"

    p = float(price)
    ss = float(sma_short)
    sl = float(sma_long)
    ds = float(distance_short_pct)
    dl = float(distance_long_pct)

    if p > ss > sl:
        if ds > 2 and dl > 2:
            return "STRONG_UP"
        return "UP"
    elif p < ss < sl:
        if ds < -2 and dl < -2:
            return "STRONG_DOWN"
        return "DOWN"
    else:
        return "NEUTRAL"


def compute_all_indicators(
    bars: Sequence[OHLCVBar],
    current_price: Decimal | float | int | None = None,
) -> dict[str, Decimal | str | None]:
    """Compute all standard indicators from a list of OHLCV bars.

    Args:
        bars: List of OHLCVBar objects in chronological order.
        current_price: Optional current price (defaults to last bar close).

    Returns:
        Dictionary of indicator names to Decimal values (or None).
        Trend fields return string values.
    """
    if not bars:
        return {}

    closes = [float(b.close) for b in bars]
    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    volumes = [float(b.volume) for b in bars]

    last_close = current_price if current_price is not None else closes[-1]

    # Returns
    ret_1d = returns(closes, 1)
    ret_5d = returns(closes, 5)
    ret_20d = returns(closes, 20)

    # Momentum
    mom_5d = momentum(closes, 5)
    mom_20d = momentum(closes, 20)

    # Moving Averages
    sma_20 = sma(closes, 20)
    sma_50 = sma(closes, 50)
    ema_20 = ema(closes, 20)
    ema_50 = ema(closes, 50)

    # Trend distances
    dist_sma20 = distance_from_sma_pct(last_close, sma_20)
    dist_sma50 = distance_from_sma_pct(last_close, sma_50)

    # RSI
    rsi_14 = rsi(closes, 14)

    # ATR
    atr_14 = atr(highs, lows, closes, 14)
    atr_pct = None
    if atr_14 is not None and last_close != 0:
        atr_pct = to_decimal((float(atr_14) / float(last_close)) * 100)

    # Volatility
    realized_vol_20 = realized_volatility(closes, 20)

    # Volume
    avg_vol_20 = avg_volume(volumes, 20)
    vol_ratio = volume_ratio(volumes[-1] if volumes else 0, avg_vol_20)
    vol_zscore = volume_zscore(volumes, volumes[-1] if volumes else 0, 20)

    # Drawdown
    cur_drawdown = drawdown(closes)

    # Trend
    trend_short = classify_trend(last_close, sma_20, sma_50, dist_sma20, dist_sma50)
    trend_medium = classify_trend(last_close, sma_50, sma_20, dist_sma50, dist_sma20)

    return {
        "return_1d": ret_1d,
        "return_5d": ret_5d,
        "return_20d": ret_20d,
        "momentum_5d": mom_5d,
        "momentum_20d": mom_20d,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "distance_sma20_pct": dist_sma20,
        "distance_sma50_pct": dist_sma50,
        "rsi_14": rsi_14,
        "atr_14": atr_14,
        "atr_pct": atr_pct,
        "realized_vol_20": realized_vol_20,
        "avg_volume_20": avg_vol_20,
        "volume_ratio": vol_ratio,
        "volume_zscore": vol_zscore,
        "current_drawdown": cur_drawdown,
        "trend_short": trend_short,
        "trend_medium": trend_medium,
    }