"""Real Alpaca market-data connectivity and feature diagnostic.

Read-only diagnostic that makes real Alpaca market data requests.
Does not submit orders or make LLM calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings
from app.market import AlpacaMarketDataGateway, MarketStateBuilder
from app.market.gateway import MarketDataError
from app.market.state import InsufficientDataError


def main() -> int:
    settings = Settings()
    print(f"Market data feed: {settings.alpaca_data_feed}")

    try:
        gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        print(f"BLOCKED — gateway initialization failed ({type(exc).__name__})")
        return 2

    symbol = "AAPL"
    try:
        # Test basic connectivity
        quote = gateway.get_latest_quote(symbol)
        trade = gateway.get_latest_trade(symbol)
        snapshot = gateway.get_snapshot(symbol)

        print("Market data: CONNECTED")
        print(f"Feed: {settings.alpaca_data_feed.upper()}")
        print(f"Symbol: {symbol}")
        print(f"Quote: bid={quote.bid_price}, ask={quote.ask_price}, spread={quote.spread}")
        print(f"Trade: price={trade.price}, size={trade.size}")

        if snapshot.daily_bar:
            print(f"Daily bar: close={snapshot.daily_bar.close}, volume={snapshot.daily_bar.volume}")

        # Build full market state
        builder = MarketStateBuilder(gateway, settings)
        state = builder.build(symbol)

        print(f"Bars retrieved: {state.bars_used}")
        print(f"Latest close: {state.latest_bar.close if state.latest_bar else 'N/A'}")

        # Print key features
        f = state.features
        print(f"RSI14: {f.rsi_14}")
        print(f"SMA20: {f.sma_20}")
        print(f"SMA50: {f.sma_50}")
        print(f"Realized vol20: {f.realized_vol_20}")
        print(f"Trend (short): {f.trend_short}")
        print(f"Trend (medium): {f.trend_medium}")
        print(f"ATR14: {f.atr_14}")
        print(f"ATR%: {f.atr_pct}")
        print(f"Volume ratio: {f.volume_ratio}")
        print(f"Current drawdown: {f.current_drawdown}")
        print(f"Data quality: {state.data_quality.status}")
        print(f"  Bars requested: {state.data_quality.bars_requested}")
        print(f"  Bars received: {state.data_quality.bars_received}")
        if state.data_quality.warnings:
            for w in state.data_quality.warnings:
                print(f"  Warning: {w}")

    except InsufficientDataError as exc:
        print(f"DEGRADED — insufficient data ({exc.bars_received}/{exc.bars_required} bars)")
        return 1
    except MarketDataError as exc:
        print(f"FAIL — market data error ({exc})")
        return 2
    except Exception as exc:
        print(f"FAIL — unexpected error ({type(exc).__name__}: {exc})")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())