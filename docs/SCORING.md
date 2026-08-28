# AlphaCouncil Scoring System (M2)

## Overview

The scoring system is the core of the M2 discovery pipeline. It transforms raw market data into explainable, directional opportunity scores that drive candidate selection for the M3 agent committee.

## Design Principles

1. **Deterministic** — Same inputs always produce same outputs
2. **Explainable** — Every score component has structured reasons
3. **Directional** — Distinguishes bullish/bearish/mixed evidence
4. **Normalized** — All components on 0-100 scale
5. **Weighted** — Configurable weights, normalized to sum=1.0
6. **Penalizes Extremes** — Volatility capped, not rewarded

## Signal Components

### 1. Momentum Signal

**Inputs**: `return_5d`, `return_20d`

```python
# 5d momentum (recent, higher weight)
if return_5d > 0.05:     score = min(100, 50 + return_5d * 500), BULLISH
elif return_5d > 0.02:   score = min(100, 50 + return_5d * 1000), BULLISH
elif return_5d < -0.05:  score = max(0, 50 + return_5d * 500), BEARISH
elif return_5d < -0.02:  score = max(0, 50 + return_5d * 1000), BEARISH
else:                     score = 50, NEUTRAL

# 20d confirmation
if return_20d > 0.10:    score += 10 (if bullish)
elif return_20d < -0.10: score -= 10 (if bearish)
```

**Reasons**: `STRONG_5D_MOMENTUM`, `POSITIVE_5D_MOMENTUM`, `NEGATIVE_5D_MOMENTUM`, `POSITIVE_20D_MOMENTUM`, `NEGATIVE_20D_MOMENTUM`

### 2. Trend Signal

**Inputs**: `distance_sma20_pct`, `distance_sma50_pct`, `trend_short`, `trend_medium`

```python
d20 = distance_sma20_pct
d50 = distance_sma50_pct

if d20 > 0 and d50 > 0:
    if d20 > 5 and d50 > 5:  score = 90, STRONG_UPTREND
    else:                     score = 70, UPTREND
elif d20 < 0 and d50 < 0:
    if d20 < -5 and d50 < -5: score = 10, STRONG_DOWNTREND
    else:                      score = 30, DOWNTREND
else:
    score = 50, MIXED  # Price between SMAs

# Trend classification confirmation
if "UP" in trend_short and "UP" in trend_medium:
    score = min(score + 10, 100), BULLISH
elif "DOWN" in trend_short and "DOWN" in trend_medium:
    score = max(score - 10, 0), BEARISH
```

**Reasons**: `STRONG_UPTREND`, `UPTREND`, `STRONG_DOWNTREND`, `DOWNTREND`, `MIXED_TREND`, `TREND_ALIGNED`

### 3. Volume Signal

**Inputs**: `volume_ratio`, `volume_zscore`

```python
vr = volume_ratio

if vr >= 2.0:      score = 85, BULLISH (if return_1d > 0) or MIXED, UNUSUAL_VOLUME
elif vr >= 1.5:    score = 70, ELEVATED_VOLUME
elif vr <= 0.5:    score = 30, LOW_VOLUME

vz = volume_zscore
if vz >= 2.0:      score = max(score, 80), VOLUME_ZSCORE_HIGH
elif vz <= -2.0:   score = min(score, 20), VOLUME_ZSCORE_LOW
```

**Reasons**: `UNUSUAL_VOLUME`, `ELEVATED_VOLUME`, `LOW_VOLUME`, `VOLUME_ZSCORE_HIGH`, `VOLUME_ZSCORE_LOW`

### 4. Volatility Signal

**Inputs**: `realized_vol_20`, `atr_pct`

**Key Design**: Rewards *moderate* volatility, penalizes extremes.

```python
vol = realized_vol_20 (annualized, log returns)

if 0.15 <= vol <= 0.40:    score = 75, HEALTHY_VOLATILITY
elif 0.10 <= vol < 0.15:   score = 60, LOW_VOLATILITY
elif 0.40 < vol <= 0.60:   score = 60, ELEVATED_VOLATILITY
elif vol > 0.60:           score = 40, EXTREME_VOLATILITY (PENALIZED)
elif vol < 0.10:           score = 30, VERY_LOW_VOLATILITY

atr_pct provides additional context:
if atr_pct > 5.0:   HIGH_ATR_PCT
elif atr_pct < 1.0: LOW_ATR_PCT
```

**Reasons**: `HEALTHY_VOLATILITY`, `LOW_VOLATILITY`, `ELEVATED_VOLATILITY`, `EXTREME_VOLATILITY`, `VERY_LOW_VOLATILITY`, `HIGH_ATR_PCT`, `LOW_ATR_PCT`

### 5. Mean Reversion Signal

**Inputs**: `rsi_14`, `distance_sma20_pct`, `distance_sma50_pct`

```python
# RSI-based
if rsi <= 30:      score = 70, BULLISH, RSI_OVERSOLD
elif rsi <= 40:    score = 60, BULLISH, RSI_LOW
elif rsi >= 70:    score = 30, BEARISH, RSI_OVERBOUGHT
elif rsi >= 60:    score = 40, BEARISH, RSI_HIGH

# Pullback in uptrend
if -3 <= d20 <= 1 and d50 > 2:
    score = max(score, 65), BULLISH, PULLBACK_IN_UPTREND
```

**Reasons**: `RSI_OVERSOLD`, `RSI_LOW`, `RSI_OVERBOUGHT`, `RSI_HIGH`, `PULLBACK_IN_UPTREND`

### 6. Liquidity Signal

**Inputs**: `dollar_volume`

```python
# Log scale: $1M=0, $10M=50, $100M=100
log_dv = log10(dollar_volume)
score = min(100, max(0, (log10(dv) - 6) * 50))

if dv >= 50M:   HIGH_LIQUIDITY
elif dv >= 10M: GOOD_LIQUIDITY
else:           MODERATE_LIQUIDITY
```

**Reasons**: `HIGH_LIQUIDITY`, `GOOD_LIQUIDITY`, `MODERATE_LIQUIDITY`

### 7. Quality Signal

**Inputs**: `data_quality_status`, `bars_received`

```python
if GOOD:        score = 100, DATA_QUALITY_GOOD
elif DEGRADED:  score = 70,  DATA_QUALITY_DEGRADED
elif INSUFFICIENT: score = 30, DATA_QUALITY_INSUFFICIENT
elif STALE:     score = 20,  DATA_STALE

if bars >= 100:     SUFFICIENT_HISTORY
elif bars >= 50:    ADEQUATE_HISTORY
```

## Weighted Aggregation

```python
weights = SignalWeights(
    momentum=0.20,
    trend=0.20,
    volume=0.15,
    volatility=0.15,
    mean_reversion=0.10,
    liquidity=0.10,
    quality=0.10,
)
# Normalized internally to sum=1.0

total = sum(score * weight for score, weight in zip(component_scores, weights))
```

## Directional Bias

```python
bullish_weight = sum(weight for name, dir if dir == BULLISH and score > 60)
bearish_weight = sum(weight for name, dir if dir == BEARISH and score < 40)

if bullish_weight > bearish_weight * 1.5:  BULLISH
elif bearish_weight > bullish_weight * 1.5: BEARISH
elif bullish > 0 and bearish > 0:           MIXED
else:                                        NEUTRAL
```

## Score Interpretation

| Total Score | Interpretation |
| --- | --- |
| 80-100 | Strong opportunity, high conviction |
| 60-79 | Moderate opportunity, worth committee review |
| 40-59 | Weak/marginal, low priority |
| 20-39 | Unfavorable, likely reject |
| 0-19 | Strong reject |

## Viability Threshold

```python
def is_viable(self) -> bool:
    return float(self.total) >= 30.0
```

Candidates below 30 are filtered out before deep analysis.

## Tie Breaking

When scores are equal, candidates are ranked by **symbol alphabetical order** (deterministic, stable).

## Configuration

Weights are configurable via `Settings`:

```python
discovery_weight_momentum = 0.20
discovery_weight_trend = 0.20
discovery_weight_volume = 0.15
discovery_weight_volatility = 0.15
discovery_weight_mean_reversion = 0.10
discovery_weight_liquidity = 0.10
discovery_weight_quality = 0.10
```

Weights are automatically normalized to sum=1.0.

## Example Output

```
#1 CRM
  Direction: BULLISH
  Score: 83.75
  Components: M:110 T:90 V:85 Vol:40 MR:50 L:100 Q:100
  Reasons:
    - STRONG_5D_MOMENTUM (22.6%)
    - POSITIVE_20D_MOMENTUM (39.5%)
    - STRONG_UPTREND (SMA20:26.1%, SMA50:41.0%)
    - UNUSUAL_VOLUME (4.4x avg)
  Data Quality: GOOD
```

## Testing

```bash
# Run scoring tests
uv run pytest tests/test_discovery_scoring.py -v

# Run signal tests
uv run pytest tests/test_discovery_signals.py -v
```

## Key Properties Verified by Tests

- **Deterministic**: Same inputs → same outputs
- **Bounded**: All components 0-100, total 0-100
- **Directional**: Bullish/bearish evidence correctly classified
- **Explainable**: Reasons match signal calculations
- **No LLM dependency**: Zero NVIDIA imports in scoring module
- **Volatility penalty**: Extreme vol (>60%) never scores >50
- **Tie breaking**: Alphabetical by symbol
- **Viability**: Scores <30 filtered out