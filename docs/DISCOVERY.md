# AlphaCouncil Discovery Pipeline (M2)

## Overview

The Discovery Pipeline is the deterministic opportunity discovery engine for AlphaCouncil M2. It answers the question:

> "Out of the market universe, which symbols are currently worth sending to the AlphaCouncil committee for deeper reasoning?"

The pipeline is **fully deterministic**, requires **zero LLM calls**, and produces a ranked **CandidateSet** that serves as the input contract for M3 (Agent Committee).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      DISCOVERY PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Universe  │───▶│  BulkScreener │───▶│ ScreeningObservation│  │
│  │  Provider   │    │ (Alpaca API)  │    │  (lightweight)    │   │
│  └─────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                   │             │
│                           ┌───────────────────────┘             │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │  Hard Filters  │                              │
│                  │ (price, liquid │                              │
│                  │  history, qual)│                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │Signal Computation│                            │
│                  │(7 components)  │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │OpportunityScore│                              │
│                  │(weighted, dir, │                              │
│                  │  reasons)      │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │PreliminaryCand.│                              │
│                  │(ranked,divers) │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │  Top-K Select  │                              │
│                  │(deep_analysis_k)│                             │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │MarketStateBuilder│                            │
│                  │   (M1 reuse)   │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │    Candidate   │                              │
│                  │(MarketState +   │                              │
│                  │  Score + Reas) │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │Final Diversifi.│                              │
│                  │(category caps) │                              │
│                  └───────┬────────┘                              │
│                           │                                     │
│                           ▼                                     │
│                  ┌────────────────┐                              │
│                  │  CandidateSet  │                              │
│                  │(final output)  │                              │
│                  └────────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### UniverseProvider

Abstract interface for symbol universe retrieval.

```python
class UniverseProvider(ABC):
    @abstractmethod
    def get_universe(self, mode: Literal["curated", "alpaca"]) -> list[str]: ...
    @abstractmethod
    def get_asset_category(self, symbol: str) -> str: ...
```

**Implementations**:
- `CuratedUniverseProvider` — 64 diversified liquid symbols (default)
- `AlpacaUniverseProvider` — Alpaca active/tradable US equities

### BulkScreener

Efficiently retrieves screening data for multiple symbols.

```python
class BulkScreener:
    def screen_symbols(
        self,
        symbols: list[str],
        timeframe: Timeframe = Timeframe.DAY,
    ) -> list[ScreeningObservation]:
        ...
```

Uses single Alpaca snapshot request per symbol, retrieves ~150 days of daily bars for indicator computation.

### ScreeningObservation

Lightweight per-symbol evidence for preliminary scoring.

```python
@dataclass
class ScreeningObservation:
    symbol: str
    as_of: datetime
    price: Decimal
    return_1d: Decimal | None
    return_5d: Decimal | None
    return_20d: Decimal | None
    volume: Decimal | None
    avg_volume_20: Decimal | None
    volume_ratio: Decimal | None
    volume_zscore: Decimal | None
    realized_vol_20: Decimal | None
    atr_pct: Decimal | None
    distance_sma20_pct: Decimal | None
    distance_sma50_pct: Decimal | None
    rsi_14: Decimal | None
    trend_short: str | None
    trend_medium: str | None
    dollar_volume: Decimal | None
    data_quality_status: str | None
    bars_received: int | None
```

### Hard Filters

Applied before scoring to eliminate ineligible symbols:

| Filter | Threshold | Rejection Reason |
| --- | --- | --- |
| Minimum Price | $5.00 | `PRICE_TOO_LOW` |
| Min Avg Dollar Volume | $5,000,000 | `LOW_LIQUIDITY` |
| Minimum History Bars | 50 | `INSUFFICIENT_HISTORY` |
| Stale Data | No price | `STALE_DATA` |
| Invalid Data | Insufficient fields | `INVALID_DATA` |
| Data Quality | DEGRADED/INSUFFICIENT/STALE | `DATA_QUALITY_DEGRADED` |

### Signal Components

| Component | Input | Output (0-100) | Direction |
| --- | --- | --- | --- |
| Momentum | return_5d, return_20d | 0-100 | BULLISH/BEARISH/NEUTRAL |
| Trend | SMA20/50 distances, trend classification | 0-100 | BULLISH/BEARISH/MIXED |
| Volume | volume_ratio, volume_zscore | 0-100 | BULLISH/MIXED |
| Volatility | realized_vol_20, atr_pct | 0-100 | NEUTRAL (penalizes extremes) |
| Mean Reversion | rsi_14, SMA distances | 0-100 | BULLISH/BEARISH |
| Liquidity | dollar_volume (log scale) | 0-100 | NEUTRAL |
| Quality | data_quality_status, bars_received | 0-100 | NEUTRAL |

### OpportunityScore

```python
@dataclass
class OpportunityScore:
    total: Decimal                    # Weighted total (0-100)
    momentum: Decimal                 # Component score
    trend: Decimal
    volume: Decimal
    volatility: Decimal
    mean_reversion: Decimal
    liquidity: Decimal
    quality: Decimal
    direction: SignalDirection        # BULLISH/BEARISH/MIXED/NEUTRAL
    reasons: tuple[str, ...]          # Structured reason codes
    reason_contributions: dict        # Approximate contributions
```

### Candidate Models

```python
@dataclass
class PreliminaryCandidate:
    symbol: str
    observation: ScreeningObservation
    score: OpportunityScore
    rank: int | None = None

@dataclass
class Candidate:
    symbol: str
    rank: int
    direction: SignalDirection
    opportunity_score: OpportunityScore
    market_state: MarketState         # Full M1 MarketState
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    data_quality_status: str | None
    generated_at: datetime
```

### CandidateSet

```python
@dataclass
class CandidateSet:
    generated_at: datetime
    universe_mode: UniverseMode
    universe_size: int
    eligible_count: int
    rejected_count: int
    preliminary_count: int
    deep_analysis_count: int
    final_count: int
    candidates: tuple[Candidate, ...]
    rejections: tuple[CandidateRejection, ...]
    runtime_ms: int
```

## Configuration

All settings in `backend/app/core/config.py` under `Settings`:

| Setting | Default | Description |
| --- | --- | --- |
| `discovery_universe_mode` | `"curated"` | `"curated"` or `"alpaca"` |
| `discovery_preliminary_k` | `20` | Preliminary ranking size |
| `discovery_deep_analysis_k` | `15` | Deep M1 analysis count |
| `discovery_final_k` | `10` | Final candidate set size |
| `discovery_min_price` | `5.0` | Minimum price filter |
| `discovery_min_avg_dollar_volume` | `5_000_000.0` | Minimum avg dollar volume |
| `discovery_min_history_bars` | `50` | Minimum bars for features |
| `discovery_max_per_group` | `3` | Max candidates per asset category |
| `discovery_deep_concurrency` | `3` | Concurrency for deep analysis |
| `discovery_weight_*` | various | Signal weights (normalized) |

## Usage

```python
from app.core.config import Settings
from app.market import AlpacaMarketDataGateway
from app.discovery import create_discovery_service

settings = Settings()
gateway = AlpacaMarketDataGateway.from_settings(settings)
service = create_discovery_service(gateway, settings)

# Run discovery with defaults
result = service.discover()

# Or override parameters
result = service.discover(
    universe_mode="alpaca",
    final_k=5,
)

print(f"Found {result.final_count} candidates")
for c in result.candidates:
    print(f"#{c.rank} {c.symbol} — {c.direction} — Score: {c.opportunity_score.total}")
    for reason in c.reasons:
        print(f"  • {reason}")
```

## Diagnostic

```bash
uv run python scripts/check_discovery.py
```

Output:
```
Discovery: PASS
Universe: 64
Eligible: 64
Rejected: 0
Deep analyzed: 6
Final candidates: 6
Runtime: 47836ms

#1 CRM
direction: BULLISH
score: 83.75
reasons:
- STRONG_5D_MOMENTUM (22.6%)
- POSITIVE_20D_MOMENTUM (39.5%)
- STRONG_UPTREND (SMA20:26.1%, SMA50:41.0%)
- UNUSUAL_VOLUME (4.4x avg)
Data Quality: GOOD

#2 NVDA
...
```

## Safety

- **READ ONLY**: No order mutations, no LLM calls
- **PAPER ONLY**: Uses existing PAPER OAuth abstraction
- **NO SECRETS**: No credentials in code, .env untracked
- **ZERO LLM CALLS**: Deterministic throughout
- **ZERO ORDERS**: No trading mutations

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Run discovery-specific tests
uv run pytest tests/test_discovery_*.py -v
```

## Extension Points

1. **Custom Universe**: Implement `UniverseProvider` for alternative data sources
2. **Custom Signals**: Add to `compute_all_signals()` in `signals.py`
3. **Custom Filters**: Extend `apply_hard_filters()` in `filters.py`
4. **Custom Diversification**: Replace `apply_diversification()` in `diversification.py`
5. **Custom Scoring**: Modify `SignalWeights` and `compute_opportunity_score()`