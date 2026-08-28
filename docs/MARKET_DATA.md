# Market Data Architecture

## Overview

AlphaCouncil's market data layer provides a clean, typed abstraction over Alpaca's market data API. The design separates brokerage/account operations from market-data operations, enabling future mocking, backtesting, and alternate providers.

## Components

### MarketDataGateway (Protocol)

Abstract interface defining the market data contract:

```python
class MarketDataGateway(ABC):
    def get_latest_quote(self, symbol: str) -> QuoteSnapshot: ...
    def get_latest_trade(self, symbol: str) -> TradeSnapshot: ...
    def get_snapshot(self, symbol: str) -> MarketSnapshot: ...
    def get_bars(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime, limit: int | None = None) -> list[OHLCVBar]: ...
    def get_daily_bars(self, symbol: str, start: datetime, end: datetime, limit: int | None = None) -> list[OHLCVBar]: ...
```

### AlpacaMarketDataGateway

Concrete implementation using `alpaca-py`:

- **StockHistoricalDataClient** for market data
- **TradingClient** (optional) for market clock
- Reuses M0 credential abstraction (`AlpacaCredentialsProvider`)
- Supports both OAuth profile and API key authentication
- Paper-only enforcement via `paper=True`

## Data Feed Configuration

Set via `ALPACA_DATA_FEED` environment variable:

| Value | Alpaca Feed | Notes |
| --- | --- | --- |
| `iex` | `DataFeed.IEX` | Free tier, default |
| `sip` | `DataFeed.SIP` | Requires SIP entitlement |
| `otc` | `DataFeed.OTC` | OTC markets |

**Default**: `iex`

The application fails with a useful diagnostic if the configured feed is unavailable (e.g., SIP without entitlement).

## Normalized Domain Models

### OHLCVBar

Single bar with validated OHLC relationships:
- `high >= max(open, close)`
- `low <= min(open, close)`
- Timezone-aware timestamps (UTC)
- Decimal for monetary precision

### QuoteSnapshot

Latest bid/ask with computed spread and midpoint:
- `spread = ask - bid`
- `midpoint = (bid + ask) / 2`
- Validation: `spread >= 0`, `bid > 0`, `ask > 0`

### TradeSnapshot

Latest trade price and size.

### MarketSnapshot

Aggregated view combining quote, trade, daily bar, and previous daily bar.

## Timeframes

- `Timeframe.DAY` → `1Day` (primary)
- `Timeframe.HOUR` → `1Hour` (optional)

Extensible for future intraday timeframes without architectural changes.

## Historical Bar Pipeline

### Retrieval

```python
bars = gateway.get_bars(
    symbol="AAPL",
    timeframe=Timeframe.DAY,
    start=datetime(2024, 1, 1),
    end=datetime(2024, 12, 31),
    limit=1000
)
```

### Validation

- Chronological ordering enforced
- Duplicate timestamp detection
- OHLC relationship validation
- Gap detection (warns if < 80% of expected trading days)

### Error Handling

- Explicit timeouts (30s default)
- Structured `MarketDataError` with status code and original exception
- No silent failures or data fabrication

## Rate Limit Awareness

- Bounded retries for 429/5xx (not yet implemented, placeholder)
- No infinite retries
- Duplicate request avoidance via request-scoped caching (future)

## Usage Example

```python
from app.core.config import Settings
from app.market import AlpacaMarketDataGateway, MarketStateBuilder

settings = Settings()
gateway = AlpacaMarketDataGateway.from_settings(settings)
builder = MarketStateBuilder(gateway, settings)

state = builder.build("AAPL", Timeframe.DAY)
print(state.features.rsi_14)
print(state.data_quality.status)
```