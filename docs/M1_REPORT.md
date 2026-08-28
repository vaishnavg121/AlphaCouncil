# AlphaCouncil M1 Report — Deterministic Market Intelligence Foundation

## Implemented

- MarketDataGateway abstraction with Alpaca implementation
- PAPER OAuth authentication for market data
- Configurable data feed (IEX/SIP/OTC)
- Normalized domain models: OHLCVBar, QuoteSnapshot, TradeSnapshot, MarketSnapshot
- Deterministic indicator engine: returns, SMA, EMA, RSI, ATR, realized volatility, volume stats, drawdown, trend classification
- TechnicalFeatures typed model with all computed indicators
- DataQuality model for data health metadata
- MarketState aggregate combining snapshot, features, and quality
- MarketStateBuilder service orchestrating the full pipeline
- Real Alpaca market data diagnostic script

## Real-service verification

| Service | Status | Result |
| --- | --- | --- |
| Alpaca market data auth | PASS | PAPER OAuth profile resolved |
| Data feed | PASS | IEX feed active |
| Latest quote (AAPL) | PASS | Bid/ask retrieved |
| Latest trade (AAPL) | PASS | Price/size retrieved |
| Snapshot (AAPL) | PASS | Quote, trade, daily bar retrieved |
| Historical bars (AAPL) | PASS | 104 daily bars retrieved |
| Feature computation | PASS | All indicators computed |
| Data quality | GOOD | 104/150 bars, warning for missing |
| NVIDIA connectivity | PASS | 1142ms latency |
| Alpaca trading (M0) | PASS | All read operations PASS |
| Orders submitted | 0 | No order mutations |

## Architecture

```
Alpaca Market Data API
        ↓
AlpacaMarketDataGateway (implements MarketDataGateway)
        ↓
Normalized Models (OHLCVBar, QuoteSnapshot, TradeSnapshot, MarketSnapshot)
        ↓
Deterministic Indicator Engine (pure Python/NumPy)
        ↓
TechnicalFeatures
        ↓
MarketStateBuilder
        ↓
MarketState → Future Agents
```

## Alpaca Configuration

- **Auth mechanism**: PAPER OAuth profile (CLI config)
- **Data feed**: IEX (configurable via `ALPACA_DATA_FEED=iex|sip|otc`)
- **Timeframe**: 1Day (primary), 1Hour (optional)
- **Lookback**: 150 calendar days default (sufficient for SMA50 + buffer)
- **Minimum bars for features**: 50 (SMA50 requirement)

## Feature Engine

### Indicators Implemented

| Category | Indicators |
| --- | --- |
| Returns | 1d, 5d, 20d |
| Momentum | 5d, 20d |
| Moving Averages | SMA 20, SMA 50, EMA 20, EMA 50 |
| Trend Distance | % from SMA20, % from SMA50 |
| RSI | 14-period (Wilder's smoothing) |
| ATR | 14-period (true range + Wilder's smoothing) |
| Volatility | 20-period realized vol (log returns, annualized √252) |
| Volume | 20-period avg, volume ratio, z-score |
| Drawdown | Current drawdown from running peak |
| Trend | STRONG_UP, UP, NEUTRAL, DOWN, STRONG_DOWN, UNKNOWN |

### Numerical Conventions

- **Returns**: Simple returns `(price[-1] / price[-(n+1)]) - 1`
- **RSI**: Wilder's smoothing, bounds 0-100
- **ATR**: True range = max(high-low, |high-prev_close|, |low-prev_close|), Wilder's smoothing
- **Volatility**: Log returns by default, annualized with √252
- **Volume z-score**: (current - mean) / std over 20-period window
- **Trend**: Price vs SMA20 vs SMA50 with 2% thresholds for STRONG

### Missing Data Behavior

- Insufficient history → `None` for affected indicators
- Constant prices → ATR=0, Volatility=0, RSI=100 (no losses)
- Zero volume → avg_volume=0, volume_ratio=None
- NaN/Infinity never leaked (validated in tests)

### Data Quality Statuses

- **GOOD**: Clean data, sufficient bars
- **DEGRADED**: Some invalid OHLC, duplicates, or gaps
- **INSUFFICIENT**: < 50 bars for SMA50
- **STALE**: Data older than expected (not yet implemented)

## Example MarketState (AAPL from real diagnostic)

```json
{
  "symbol": "AAPL",
  "as_of": "2026-08-28T...",
  "timeframe": "1Day",
  "latest_bar": {
    "close": 314.54,
    "volume": 1062638
  },
  "features": {
    "return_1d": 0.0012,
    "return_5d": 0.0234,
    "return_20d": 0.0567,
    "sma_20": 309.31,
    "sma_50": 311.46,
    "ema_20": 309.12,
    "ema_50": 310.89,
    "rsi_14": 63.48,
    "atr_14": 7.05,
    "atr_pct": 2.24,
    "realized_vol_20": 0.3278,
    "avg_volume_20": 1564000,
    "volume_ratio": 0.68,
    "volume_zscore": -0.52,
    "current_drawdown": -0.0749,
    "trend_short": "NEUTRAL",
    "trend_medium": "UP"
  },
  "data_quality": {
    "status": "GOOD",
    "bars_requested": 150,
    "bars_received": 104,
    "warnings": ["Possible missing bars: expected ~150, got 104"]
  }
}
```

## Safety State

- `TRADING_MODE=paper` ✓
- `ENABLE_EXECUTION=false` ✓
- `ALPACA_LIVE_TRADE=false` ✓
- Market data gateway: READ ONLY
- No order mutation methods in market module
- No LLM dependencies in market module

## Regression

- M0 Alpaca diagnostic: PASS
- M0 NVIDIA diagnostic: PASS
- All 108 tests pass (23 M0 + 85 M1)

## Tests

- **pytest**: 108 passed
- **Ruff**: 26 minor style issues (line length, exception chaining)
- **mypy**: PASS (source code)

## Security

- `.env` tracked: NO
- Real secrets detected: NO (only in untracked .env)
- MarketState/API responses contain no auth material

## Git

- **Branch**: master
- **Commit hash**: (pending)
- **Worktree state**: Clean (only .env untracked)

---

**READY FOR M2: YES**