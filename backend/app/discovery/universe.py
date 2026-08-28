"""Universe provider for M2 discovery.

Provides abstractions for obtaining the tradable symbol universe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from app.core.config import Settings
from app.market.gateway import MarketDataGateway


class UniverseProvider(ABC):
    """Abstract universe provider interface."""

    @abstractmethod
    def get_universe(self, mode: Literal["curated", "alpaca"] = "curated") -> list[str]:
        """Get the list of symbols in the universe.

        Args:
            mode: Universe selection mode.

        Returns:
            List of normalized symbols.
        """
        ...

    @abstractmethod
    def get_asset_category(self, symbol: str) -> str:
        """Get asset category for diversification (EQUITY, ETF, UNKNOWN)."""
        ...


class CuratedUniverseProvider(UniverseProvider):
    """Curated liquid universe for reliable hackathon/demo screening.

    Contains diversified, highly liquid stocks and ETFs across sectors.
    """

    # Default curated universe - diversified across sectors
    DEFAULT_UNIVERSE: tuple[str, ...] = (
        # Broad market ETFs
        "SPY", "QQQ", "IWM", "DIA", "VTI",
        # Technology
        "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "AVGO", "ADBE", "CRM", "ORCL",
        # Semiconductors
        "AMD", "INTC", "TSM", "MU", "QCOM",
        # Financials
        "JPM", "BAC", "WFC", "GS", "MS", "V", "MA",
        # Healthcare
        "JNJ", "UNH", "PFE", "ABBV", "MRK", "TMO", "ABT",
        # Consumer
        "WMT", "COST", "HD", "PG", "KO", "PEP", "MCD",
        # Industrials
        "CAT", "GE", "HON", "UPS", "BA", "RTX",
        # Energy
        "XOM", "CVX", "COP", "EOG", "SLB",
        # Communications
        "DIS", "NFLX", "TMUS", "VZ",
        # Materials
        "LIN", "APD", "FCX", "NEM",
        # Utilities / REITs
        "NEE", "DUK", "SO", "O",
    )

    def __init__(self, universe: tuple[str, ...] | None = None) -> None:
        self._universe = universe or self.DEFAULT_UNIVERSE

    def get_universe(self, mode: Literal["curated", "alpaca"] = "curated") -> list[str]:
        if mode == "curated":
            return list(self._universe)
        raise ValueError("CuratedUniverseProvider only supports 'curated' mode")

    def get_asset_category(self, symbol: str) -> str:
        """Return asset category for known symbols."""
        etf_symbols = {"SPY", "QQQ", "IWM", "DIA", "VTI", "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLB", "XLC"}
        if symbol in etf_symbols:
            return "ETF"
        return "EQUITY"


class AlpacaUniverseProvider(UniverseProvider):
    """Alpaca-backed universe provider using asset metadata."""

    def __init__(
        self,
        gateway: MarketDataGateway,
        settings: Settings | None = None,
    ) -> None:
        if gateway is None:
            raise ValueError("AlpacaUniverseProvider requires a MarketDataGateway")
        self._gateway = gateway
        self._settings = settings or Settings()
        self._category_cache: dict[str, str] = {}

    def get_universe(self, mode: Literal["curated", "alpaca"] = "alpaca") -> list[str]:
        if mode != "alpaca":
            raise ValueError("AlpacaUniverseProvider only supports 'alpaca' mode")

        # Use the gateway's trading client to get assets
        if hasattr(self._gateway, "_trading_client") and self._gateway._trading_client:
            try:
                assets = self._gateway._trading_client.get_all_assets()
                symbols = []
                for asset in assets:
                    if (
                        getattr(asset, "tradable", False)
                        and getattr(asset, "status", "") == "active"
                        and getattr(asset, "asset_class", "") == "us_equity"
                    ):
                        symbol = getattr(asset, "symbol", "")
                        if symbol and self._is_valid_symbol(symbol):
                            symbols.append(symbol)
                return symbols
            except Exception:
                pass
        return []

    def get_asset_category(self, symbol: str) -> str:
        if symbol in self._category_cache:
            return self._category_cache[symbol]

        if hasattr(self._gateway, "_trading_client") and self._gateway._trading_client:
            try:
                asset = self._gateway._trading_client.get_asset(symbol)
                asset_class = getattr(asset, "asset_class", "")
                exchange = getattr(asset, "exchange", "")
                # Heuristic: ETFs often trade on ARCA
                if exchange in ("ARCA", "BATS") or "ETF" in str(getattr(asset, "name", "")).upper():
                    self._category_cache[symbol] = "ETF"
                    return "ETF"
            except Exception:
                pass

        self._category_cache[symbol] = "EQUITY"
        return "EQUITY"

    @staticmethod
    def _is_valid_symbol(symbol: str) -> bool:
        """Basic symbol validation."""
        if not symbol or not symbol.isalpha():
            return False
        if len(symbol) > 5:
            return False
        # Exclude obvious leveraged/inverse products
        if any(x in symbol for x in ["UP", "DOWN", "BULL", "BEAR", "2X", "3X", "SHORT"]):
            return False
        return True


def create_universe_provider(
    mode: Literal["curated", "alpaca"],
    gateway: MarketDataGateway | None = None,
    settings: Settings | None = None,
) -> UniverseProvider:
    """Factory function to create universe provider."""
    if mode == "curated":
        return CuratedUniverseProvider()
    if mode == "alpaca":
        if gateway is None:
            raise ValueError("Alpaca universe mode requires a MarketDataGateway")
        return AlpacaUniverseProvider(gateway, settings)
    raise ValueError(f"Unknown universe mode: {mode}")