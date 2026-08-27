"""Read-only paper-account connectivity diagnostic using AlphaCouncil's gateway."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.alpaca.auth import AlpacaCredentialsProvider
from app.alpaca.gateway import AlpacaGateway
from app.core.config import Settings
from app.core.errors import CredentialsUnavailableError


def main() -> int:
    settings = Settings()
    credentials = AlpacaCredentialsProvider(settings).resolve()
    print(f"Alpaca auth: {credentials.auth_type}")
    print("Environment: PAPER")
    try:
        gateway = AlpacaGateway.from_settings(settings)
        gateway.get_account()
        gateway.get_clock()
        gateway.get_asset("AAPL")
        gateway.list_positions()
        gateway.list_orders()
    except CredentialsUnavailableError:
        print("BLOCKED — no complete paper-safe Alpaca credential bundle")
        return 2
    except Exception as exc:  # pragma: no cover - requires external credentials/network
        print(f"FAIL — read-only Alpaca diagnostic unavailable ({type(exc).__name__})")
        return 2

    print("Account: CONNECTED")
    print("Clock: READ OK")
    print("Data: CONNECTED")
    print("AAPL: RESOLVED")
    print("Positions: READ OK")
    print("Orders: READ OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
