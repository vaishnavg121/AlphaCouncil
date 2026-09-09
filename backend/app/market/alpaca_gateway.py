"""Alpaca market data gateway implementation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from alpaca.data import StockHistoricalDataClient
from alpaca.data.enums import DataFeed
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient

from app.alpaca.auth import AlpacaAuthType, AlpacaCredentialsProvider
from app.core.config import Settings
from app.core.errors import CredentialsUnavailableError
from app.market.gateway import MarketDataError, MarketDataGateway
from app.market.models import (
    MarketSnapshot,
    OHLCVBar,
    QuoteSnapshot,
    Timeframe,
    TradeSnapshot,
)


class AlpacaMarketDataGateway(MarketDataGateway):
    """Alpaca implementation of the market data gateway."""

    def __init__(
        self,
        data_client: StockHistoricalDataClient,
        trading_client: TradingClient | None = None,
    ) -> None:
        self._data_client = data_client
        self._trading_client = trading_client

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaMarketDataGateway:
        """Create gateway from settings using the existing credential abstraction."""
        credentials = AlpacaCredentialsProvider(settings).require()

        if credentials.auth_type is AlpacaAuthType.OAUTH_PROFILE and credentials.oauth_token is not None:
            data_client = StockHistoricalDataClient(
                oauth_token=credentials.oauth_token.get_secret_value(),
            )
            trading_client = TradingClient(
                oauth_token=credentials.oauth_token.get_secret_value(),
                paper=True,
            )
        elif (
            credentials.auth_type is AlpacaAuthType.API_KEYS
            and credentials.api_key is not None
            and credentials.secret_key is not None
        ):
            data_client = StockHistoricalDataClient(
                api_key=credentials.api_key.get_secret_value(),
                secret_key=credentials.secret_key.get_secret_value(),
            )
            trading_client = TradingClient(
                api_key=credentials.api_key.get_secret_value(),
                secret_key=credentials.secret_key.get_secret_value(),
                paper=True,
            )
        else:
            raise CredentialsUnavailableError(
                "No complete paper-safe Alpaca credential bundle is available"
            )

        return cls(data_client=data_client, trading_client=trading_client)

    def _get_data_feed(self, settings: Settings | None = None) -> DataFeed:
        """Get the configured data feed, defaulting to IEX."""
        if settings is not None:
            feed_map = {
                "iex": DataFeed.IEX,
                "sip": DataFeed.SIP,
                "otc": DataFeed.OTC,
            }
            return feed_map.get(settings.alpaca_data_feed, DataFeed.IEX)
        return DataFeed.IEX

    def get_latest_quote(self, symbol: str) -> QuoteSnapshot:
        """Get the latest quote for a symbol."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            response = self._data_client.get_stock_latest_quote(request)
            quote = response[symbol]

            return QuoteSnapshot(
                symbol=symbol,
                timestamp=quote.timestamp.replace(tzinfo=UTC) if quote.timestamp.tzinfo is None else quote.timestamp,
                bid_price=Decimal(str(quote.bid_price)),
                ask_price=Decimal(str(quote.ask_price)),
                bid_size=int(quote.bid_size) if quote.bid_size is not None else None,
                ask_size=int(quote.ask_size) if quote.ask_size is not None else None,
            )
        except Exception as e:
            raise MarketDataError(
                f"Failed to get latest quote for {symbol}: {e}", original=e
            ) from e

    def get_latest_trade(self, symbol: str) -> TradeSnapshot:
        """Get the latest trade for a symbol."""
        try:
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            response = self._data_client.get_stock_latest_trade(request)
            trade = response[symbol]

            return TradeSnapshot(
                symbol=symbol,
                timestamp=trade.timestamp.replace(tzinfo=UTC) if trade.timestamp.tzinfo is None else trade.timestamp,
                price=Decimal(str(trade.price)),
                size=int(trade.size) if trade.size is not None else None,
            )
        except Exception as e:
            raise MarketDataError(
                f"Failed to get latest trade for {symbol}: {e}", original=e
            ) from e

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Get an aggregated market snapshot for a symbol."""
        try:
            settings = Settings()
            feed = self._get_data_feed(settings)
            request = StockSnapshotRequest(symbol_or_symbols=symbol, feed=feed)
            response = self._data_client.get_stock_snapshot(request)
            snapshot = response[symbol]

            quote = None
            if snapshot.latest_quote is not None:
                q = snapshot.latest_quote
                quote = QuoteSnapshot(
                    symbol=symbol,
                    timestamp=q.timestamp.replace(tzinfo=UTC) if q.timestamp.tzinfo is None else q.timestamp,
                    bid_price=Decimal(str(q.bid_price)),
                    ask_price=Decimal(str(q.ask_price)),
                    bid_size=int(q.bid_size) if q.bid_size is not None else None,
                    ask_size=int(q.ask_size) if q.ask_size is not None else None,
                )

            trade = None
            if snapshot.latest_trade is not None:
                t = snapshot.latest_trade
                trade = TradeSnapshot(
                    symbol=symbol,
                    timestamp=t.timestamp.replace(tzinfo=UTC) if t.timestamp.tzinfo is None else t.timestamp,
                    price=Decimal(str(t.price)),
                    size=int(t.size) if t.size is not None else None,
                )

            daily_bar = None
            if snapshot.daily_bar is not None:
                b = snapshot.daily_bar
                daily_bar = OHLCVBar(
                    symbol=symbol,
                    timestamp=b.timestamp.replace(tzinfo=UTC) if b.timestamp.tzinfo is None else b.timestamp,
                    open=Decimal(str(b.open)),
                    high=Decimal(str(b.high)),
                    low=Decimal(str(b.low)),
                    close=Decimal(str(b.close)),
                    volume=int(b.volume),
                    trade_count=int(b.trade_count) if b.trade_count else None,
                    vwap=Decimal(str(b.vwap)) if b.vwap else None,
                )

            previous_daily_bar = None
            if snapshot.previous_daily_bar is not None:
                b = snapshot.previous_daily_bar
                previous_daily_bar = OHLCVBar(
                    symbol=symbol,
                    timestamp=b.timestamp.replace(tzinfo=UTC) if b.timestamp.tzinfo is None else b.timestamp,
                    open=Decimal(str(b.open)),
                    high=Decimal(str(b.high)),
                    low=Decimal(str(b.low)),
                    close=Decimal(str(b.close)),
                    volume=int(b.volume),
                    trade_count=int(b.trade_count) if b.trade_count else None,
                    vwap=Decimal(str(b.vwap)) if b.vwap else None,
                )

            return MarketSnapshot(
                symbol=symbol,
                quote=quote,
                trade=trade,
                daily_bar=daily_bar,
                previous_daily_bar=previous_daily_bar,
            )
        except Exception as e:
            raise MarketDataError(
                f"Failed to get snapshot for {symbol}: {e}", original=e
            ) from e

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Get historical bars for a symbol within a date range."""
        try:
            settings = Settings()
            feed = self._get_data_feed(settings)

            tf_map = {
                Timeframe.DAY: TimeFrame.Day,
                Timeframe.HOUR: TimeFrame.Hour,
            }
            alpaca_timeframe = tf_map[timeframe]

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=alpaca_timeframe,
                start=start,
                end=end,
                limit=limit,
                feed=feed,
            )
            response = self._data_client.get_stock_bars(request)

            bars = []
            for bar in response[symbol]:
                bars.append(
                    OHLCVBar(
                        symbol=symbol,
                        timestamp=bar.timestamp.replace(tzinfo=UTC) if bar.timestamp.tzinfo is None else bar.timestamp,
                        open=Decimal(str(bar.open)),
                        high=Decimal(str(bar.high)),
                        low=Decimal(str(bar.low)),
                        close=Decimal(str(bar.close)),
                        volume=int(bar.volume),
                        trade_count=int(bar.trade_count) if bar.trade_count else None,
                        vwap=Decimal(str(bar.vwap)) if bar.vwap else None,
                    )
                )

            return bars
        except Exception as e:
            raise MarketDataError(
                f"Failed to get bars for {symbol}: {e}", original=e
            ) from e

    def get_daily_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Get daily bars for a symbol (convenience method for 1Day timeframe)."""
        return self.get_bars(symbol, Timeframe.DAY, start, end, limit)
