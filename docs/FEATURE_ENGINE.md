# Deterministic Feature Engine

## Principle

**LLMs MUST NOT calculate market indicators.**

Python computes all numerical features deterministically. LLMs only interpret the computed values.

## Indicators Reference

### Returns

| Function | Formula | Period |
| --- | --- | --- |
| `returns(prices, 1)` | `prices[-1] / prices[-2] - 1` | 1 |
| `returns(prices, 5)` | `prices[-1] / prices[-6] - 1` | 5 |
| `returns(prices, 20)` | `prices[-1] / prices[-21] - 1` | 20 |

Returns `None` if insufficient data or division by zero.

### Momentum

| Function | Formula | Period |
| --- | --- | --- |
| `momentum(prices, 5)` | `prices[-1] - prices[-6]` | 5 |
| `momentum(prices, 20)` | `prices[-1] - prices[-21]` | 20 |

### Moving Averages

| Function | Type | Period |
| --- | --- | --- |
| `sma(values, 20)` | Simple | 20 |
| `sma(values, 50)` | Simple | 50 |
| `ema(values, 20)` | Exponential (Wilder's α=2/(n+1)) | 20 |
| `ema(values, 50)` | Exponential (Wilder's α=2/(n+1)) | 50 |

**EMA Implementation**: `ema_val = α * price + (1-α) * ema_val` starting from first value.

### Trend Distance

| Function | Formula |
| --- | --- |
| `distance_from_sma_pct(price, sma_20)` | `(price - sma_20) / sma_20 * 100` |
| `distance_from_sma_pct(price, sma_50)` | `(price - sma_50) / sma_50 * 100` |

Returns `None` if SMA is `None` or zero.

### RSI (14)

**Algorithm**: Wilder's smoothing
1. `deltas = diff(prices)`
2. `gains = max(deltas, 0)`, `losses = max(-deltas, 0)`
3. `avg_gain = mean(gains[:14])`, `avg_loss = mean(losses[:14])`
4. For remaining: `avg_gain = (avg_gain * 13 + gain) / 14`
5. `RS = avg_gain / avg_loss` (if `avg_loss == 0` → RSI = 100)
6. `RSI = 100 - 100 / (1 + RS)`

**Bounds**: 0-100 when defined.

### ATR (14)

**True Range**: `max(high - low, |high - prev_close|, |low - prev_close|)`

**Algorithm**: Wilder's smoothing on true ranges
1. Compute true ranges for each bar
2. `atr = mean(true_ranges[:14])`
3. For remaining: `atr = (atr * 13 + tr) / 14`

**ATR%**: `atr_14 / current_price * 100`

### Realized Volatility (20)

**Log Returns** (default): `diff(log(prices))`
**Simple Returns** (optional): `diff(prices) / prices[:-1]`

**Formula**: `std(returns, ddof=1) * sqrt(252)` (annualized)

**Returns**: `None` if < 2 returns.

### Volume

| Function | Formula |
| --- | --- |
| `avg_volume(volumes, 20)` | `mean(volumes[-20:])` |
| `volume_ratio(current, avg)` | `current / avg` (None if avg=0) |
| `volume_zscore(volumes, current, 20)` | `(current - mean) / std` (None if std=0) |

### Drawdown

**Current Drawdown**: `(current_price - running_peak) / running_peak`

Returns negative value (or 0 at peak). `None` if no prices.

### Trend Classification

```python
classify_trend(price, sma_20, sma_50, dist_20_pct, dist_50_pct) -> Trend
```

| Trend | Condition |
| --- | --- |
| STRONG_UP | price > SMA20 > SMA50, dist_20 > 2%, dist_50 > 2% |
| UP | price > SMA20 > SMA50 |
| NEUTRAL | price between SMAs or SMAs flat |
| DOWN | price < SMA20 < SMA50 |
| STRONG_DOWN | price < SMA20 < SMA50, dist_20 < -2%, dist_50 < -2% |
| UNKNOWN | Any SMA/distance is None |

## TechnicalFeatures Model

All fields are `Decimal | None` except trend fields (`Trend` enum):

```python
TechnicalFeatures(
    # Returns
    return_1d, return_5d, return_20d,
    # Momentum
    momentum_5d, momentum_20d,
    # Moving Averages
    sma_20, sma_50, ema_20, ema_50,
    # Trend Distance
    distance_sma20_pct, distance_sma50_pct,
    # RSI
    rsi_14,
    # ATR
    atr_14, atr_pct,
    # Volatility
    realized_vol_20,
    # Volume
    avg_volume_20, volume_ratio, volume_zscore,
    # Drawdown
    current_drawdown,
    # Trend
    trend_short, trend_medium
)
```

## Data Quality Model

```python
DataQuality(
    status: DataQualityStatus,  # GOOD | DEGRADED | INSUFFICIENT | STALE
    bars_requested: int,
    bars_received: int,
    missing_values: int,
    duplicate_bars: int,
    stale: bool,
    warnings: tuple[str, ...],
    history_start: datetime | None,
    history_end: datetime | None
)
```

## MarketState Model

Complete deterministic state for agent consumption:

```python
MarketState(
    symbol: str,
    as_of: datetime,
    timeframe: Timeframe,
    snapshot: MarketSnapshot,
    latest_bar: OHLCVBar | None,
    features: TechnicalFeatures,
    data_quality: DataQuality,
    bars_used: int,
    history_start: datetime | None,
    history_end: datetime | None,
    market_open: bool | None
)
```

## MarketStateBuilder

Orchestrates the full pipeline:

```python
builder = MarketStateBuilder(gateway, settings, default_lookback_days=150)
state = builder.build("AAPL", Timeframe.DAY, lookback_days=150)
```

### Responsibilities

1. Normalize symbol (uppercase)
2. Calculate date range (lookback calendar days)
3. Retrieve historical bars
4. Validate bars (duplicates, OHLC, gaps)
5. Retrieve current snapshot
6. Determine current price (trade → quote midpoint → last bar close)
7. Compute all indicators
8. Build TechnicalFeatures
9. Determine data quality
10. Produce MarketState

### Error Handling

- `InsufficientDataError`: < 50 bars for SMA50
- `MarketDataError`: Provider failures
- Never fabricates missing bars
- Never forward-fills prices

## Numerical Edge Cases Handled

| Case | Behavior |
| --- | --- |
| Insufficient history | Returns `None` for affected indicators |
| Constant prices | ATR=0, Vol=0, RSI=100 |
| Zero volume | avg_vol=0, ratio=None, zscore=None |
| Zero denominator | Returns `None` |
| Single bar input | Most indicators `None` |
| Extreme values | Decimal precision, no overflow |

## Invariants (Tested)

- `high >= max(open, close)` for all bars
- `low <= min(open, close)` for all bars
- `ATR >= 0`
- `Realized Volatility >= 0`
- `RSI ∈ [0, 100]` when defined
- `Drawdown <= 0`
- `Bid/Ask spread >= 0` when quote valid
- No NaN/Infinity in any output

## No LLM Dependency

The market module has zero imports from NVIDIA/LLM provider. Verified by safety tests.