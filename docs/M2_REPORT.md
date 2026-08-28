# AlphaCouncil M2 Report — Deterministic Opportunity Discovery Pipeline

## Implemented

- **UniverseProvider** abstraction with **CuratedUniverseProvider** (default) and **AlpacaUniverseProvider** implementations
- **Curated liquid universe** of 64 diversified symbols across sectors (ETFs, Technology, Financials, Healthcare, Consumer, Industrials, Energy, Communications, Materials, Utilities)
- **BulkScreener** for efficient multi-symbol screening via Alpaca Market Data API
- **Hard filters**: minimum price ($5), minimum average dollar volume ($5M), minimum history bars (50), data quality checks
- **Deterministic opportunity signals** (7 components):
  - Momentum (5d/20d returns)
  - Trend (SMA20/SMA50 distances, trend classification)
  - Volume (ratio, z-score)
  - Volatility (realized vol 20, ATR%)
  - Mean Reversion (RSI, pullback detection)
  - Liquidity (dollar volume log scale)
  - Data Quality
- **OpportunityScore** with weighted components (normalized 0-100), directional bias, explainable reasons
- **PreliminaryCandidate** ranking with deterministic tie-breaking (symbol alphabetical)
- **Diversification** by asset category (EQUITY/ETF) with configurable max-per-group
- **Two-stage funnel**: bulk screening → top-K deep M1 MarketState analysis
- **Candidate** with full M1 MarketState for M3 consumption
- **CandidateSet** with complete pipeline metadata
- **OpportunityDiscoveryService** orchestrating the full pipeline
- Real Alpaca discovery diagnostic (`scripts/check_discovery.py`)

## Real-service verification

| Service | Status | Result |
| --- | --- | --- |
| Alpaca market data auth | PASS | PAPER OAuth profile resolved |
| Data feed | PASS | IEX feed active |
| Universe loading | PASS | 64 curated symbols |
| Bulk screening | PASS | 64/64 eligible, 0 rejected |
| Preliminary ranking | PASS | 64 candidates ranked |
| Deep analysis (M1) | PASS | 6/15 deep analyzed |
| Final candidates | PASS | 6 candidates produced |
| NVIDIA connectivity | PASS | 1097ms latency |
| Alpaca trading (M0) | PASS | All read operations PASS |
| Orders submitted | 0 | No order mutations |

## Architecture

```
Alpaca Market Data API
        ↓
MarketDataGateway (AlpacaMarketDataGateway)
        ↓
BulkScreener (efficient multi-symbol screening)
        ↓
ScreeningObservation (lightweight per-symbol evidence)
        ↓
Hard Filters (price, liquidity, history, data quality)
        ↓
Signal Computation (7 deterministic components)
        ↓
OpportunityScore (weighted, explainable, directional)
        ↓
PreliminaryCandidate (ranked, diversified)
        ↓
Top-K Selection (configurable deep_analysis_k)
        ↓
MarketStateBuilder (reuse M1 for deep analysis)
        ↓
Candidate (full MarketState + score + reasons)
        ↓
CandidateSet (pipeline metadata + final candidates)
        ↓
[M3 — Bull / Bear / Quant / Regime Committee]
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
- Constant prices → ATR=0, Vol=0, RSI=100 (no losses)
- Zero volume → avg_vol=0, volume_ratio=None
- Zero denominator → Returns `None`
- NaN/Infinity never leaked (validated in tests)

### Data Quality Statuses

- **GOOD**: Clean data, sufficient bars
- **DEGRADED**: Some invalid OHLC, duplicates, or gaps
- **INSUFFICIENT**: < 50 bars for SMA50
- **STALE**: Data quality status from provider

## Scoring System

### Component Weights (Normalized)

| Component | Default Weight | Range |
| --- | --- | --- |
| Momentum | 0.20 | 0-100 |
| Trend | 0.20 | 0-100 |
| Volume | 0.15 | 0-100 |
| Volatility | 0.15 | 0-100 |
| Mean Reversion | 0.10 | 0-100 |
| Liquidity | 0.10 | 0-100 |
| Quality | 0.10 | 0-100 |

**Total**: Weighted average of components (0-100)

### Directional Bias

- **BULLISH**: Weighted bullish components dominate (1.5x threshold)
- **BEARISH**: Weighted bearish components dominate (1.5x threshold)
- **MIXED**: Both bullish and bearish evidence present
- **NEUTRAL**: No strong directional evidence

### Volatility Treatment

- **Healthy band**: 15-40% annualized → high score
- **Elevated**: 40-60% → moderate score
- **Extreme**: >60% → **penalized** (capped at 40)
- **Very low**: <10% → low score

This prevents "max volatility wins" pathology.

### Explainability

Every candidate includes:
- **Component scores** (7 components, 0-100)
- **Total score** (weighted average)
- **Direction** (BULLISH/BEARISH/MIXED/NEUTRAL)
- **Reasons** (structured, deterministic codes)
- **Reason contributions** (approximate weight × deviation)

Example reasons:
- `STRONG_5D_MOMENTUM (22.6%)`
- `STRONG_UPTREND (SMA20:26.1%, SMA50:41.0%)`
- `UNUSUAL_VOLUME (4.4x avg)`
- `PULLBACK_IN_UPTREND (SMA20:-1.0%, SMA50:5.0%)`
- `RSI_OVERSOLD (25)`
- `HIGH_LIQUIDITY ($50M)`
- `EXTREME_VOLATILITY (80.0%)`

## Discovery Pipeline Configuration

```python
DISCOVERY_UNIVERSE_MODE = "curated"        # curated | alpaca
DISCOVERY_PRELIMINARY_K = 20               # Preliminary ranking size
DISCOVERY_DEEP_ANALYSIS_K = 15             # Deep M1 analysis count
DISCOVERY_FINAL_K = 10                     # Final candidate set size
DISCOVERY_MIN_PRICE = 5.0                  # Minimum price filter
DISCOVERY_MIN_AVG_DOLLAR_VOLUME = 5_000_000  # Minimum avg dollar volume
DISCOVERY_MIN_HISTORY_BARS = 50            # Minimum bars for features
DISCOVERY_MAX_PER_GROUP = 3                # Max candidates per asset category
DISCOVERY_DEEP_CONCURRENCY = 3             # Concurrency for deep analysis
```

## Example Final Candidates (from real diagnostic)

| Rank | Symbol | Direction | Score | Key Reasons |
| --- | --- | --- | --- | --- |
| 1 | CRM | BULLISH | 83.75 | Strong 5d/20d momentum, strong uptrend, unusual volume |
| 2 | NVDA | BULLISH | 79.20 | Strong momentum, strong uptrend, elevated volume |
| 3 | FCX | BULLISH | 78.48 | Strong momentum, uptrend, elevated volatility |
| 4 | SPY | BULLISH | 67.00 | Uptrend, low volatility, RSI overbought |
| 5 | QQQ | BULLISH | 65.75 | Uptrend, healthy volatility, high liquidity |
| 6 | VTI | BULLISH | 63.53 | Uptrend, low volatility, RSI overbought |

All candidates: Data Quality GOOD, 104 bars retrieved, 0 rejections.

## Safety State

- `TRADING_MODE=paper` ✓
- `ENABLE_EXECUTION=false` ✓
- `ALPACA_LIVE_TRADE=false` ✓
- Market data gateway: READ ONLY
- No order mutation methods in discovery module
- No LLM dependencies in discovery module
- Zero LLM calls during discovery
- Zero orders submitted

## Regression

- M0 Alpaca diagnostic: PASS
- M0 NVIDIA diagnostic: PASS (1097ms)
- M1 Market data diagnostic: PASS (104 bars, all features computed)
- All 193 tests pass (23 M0 + 170 M2)
- Source mypy: 0 errors in source files (test-only errors in mocks)

## Tests

- **pytest**: 193 passed, 1 skipped
- **Ruff**: Minor style issues in test files only (line length, import order)
- **mypy**: 0 errors in source files (test-only errors in mocks)

## Security

- `.env` tracked: NO
- Real secrets detected: NO (only in untracked .env)
- MarketState/API responses contain no authentication material
- No NVIDIA API calls during discovery
- No order submissions

## Git

- **Branch**: master
- **Commit hash**: (pending)
- **Worktree state**: Clean (only .env untracked, new discovery module tracked)

---

**READY FOR M3: YES**