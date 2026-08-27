"""Safe local PRE-M0 diagnostic; it never prints secrets or calls external services."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.alpaca.auth import AlpacaCredentialsProvider
from app.core.config import Settings


def status(present: bool) -> str:
    return "CONFIGURED" if present else "MISSING"


def main() -> int:
    settings = Settings()
    packages = ("alpaca", "fastapi", "numpy", "polars", "pydantic_settings")

    print(f"Python: {sys.version.split()[0]}")
    print(f"TRADING_MODE: {settings.trading_mode}")
    print(f"ENABLE_EXECUTION: {str(settings.enable_execution).lower()}")
    print(f"ALPACA_LIVE_TRADE: {str(settings.alpaca_live_trade).lower()}")
    alpaca_credentials = AlpacaCredentialsProvider(settings).resolve()
    print(f"Alpaca auth: {alpaca_credentials.auth_type}")
    print(f"Alpaca environment API keys: {status(settings.alpaca_credentials_configured)}")
    print(f"NVIDIA credentials: {status(settings.nvidia_credentials_configured)}")
    for package in packages:
        print(f"{package}: {status(importlib.util.find_spec(package) is not None)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
