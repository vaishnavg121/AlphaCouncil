"""Read-only paper-account connectivity diagnostic.

This is intentionally not run by tests and contains no order mutation methods.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from alpaca.trading.client import TradingClient
from alpaca.trading.models import Asset, Clock, TradeAccount

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings


def main() -> int:
    settings = Settings()
    if not settings.alpaca_credentials_configured:
        print("BLOCKED — ALPACA_API_KEY and ALPACA_SECRET_KEY REQUIRED")
        return 2

    assert settings.alpaca_api_key is not None
    assert settings.alpaca_secret_key is not None
    client = TradingClient(
        settings.alpaca_api_key.get_secret_value(),
        settings.alpaca_secret_key.get_secret_value(),
        paper=True,
    )
    try:
        account = cast(TradeAccount, client.get_account())
        clock = cast(Clock, client.get_clock())
        asset = cast(Asset, client.get_asset("AAPL"))
    except Exception as exc:  # pragma: no cover - requires external credentials/network
        print(f"BLOCKED — read-only Alpaca diagnostic unavailable ({type(exc).__name__})")
        return 2

    print("PASS — Alpaca paper account read access")
    print(f"Account status: {account.status}")
    print(f"Market open: {clock.is_open}")
    print(f"AAPL tradable: {asset.tradable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
