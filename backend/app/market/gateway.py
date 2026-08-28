"""Market data gateway abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.market.models import (
    MarketSnapshot,
    OHLCVBar,
    QuoteSnapshot,
    Timeframe,
    TradeSnapshot,
)


class MarketDataGateway(ABC):
    """Abstract market data gateway interface.

    This protocol allows for multiple implementations (Alpaca, mock, recorded data,
    backtesting) without rewriting the feature engine.
    """

    @abstractmethod
    def get_latest_quote(self, symbol: str) -> QuoteSnapshot:
        """Get the latest quote for a symbol."""
        ...

    @abstractmethod
    def get_latest_trade(self, symbol: str) -> TradeSnapshot:
        """Get the latest trade for a symbol."""
        ...

    @abstractmethod
    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get an aggregated market snapshot for a symbol."""
        ...

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Get historical bars for a symbol within a date range.

        Args:
            symbol: The symbol to retrieve bars for.
            timeframe: The bar timeframe.
            start: Start datetime (inclusive).
            end: End datetime (inclusive).
            limit: Maximum number of bars to return.

        Returns:
            List of OHLCVBar objects in chronological order.
        """
        ...

    @abstractmethod
    def get_daily_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Get daily bars for a symbol (convenience method for 1Day timeframe)."""
        ...


class MarketDataError(RuntimeError):
    """Raised when market data operations fail."""

    def __init__(self, message: str, status_code: int | None = None, original: Exception | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.original = original