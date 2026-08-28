"""Tests for market domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    OHLCVBar,
    QuoteSnapshot,
    TechnicalFeatures,
    Timeframe,
    TradeSnapshot,
    Trend,
)


class TestOHLCVBar:
    def test_valid_ohlcv_bar(self) -> None:
        bar = OHLCVBar(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            open=Decimal("150.0"),
            high=Decimal("155.0"),
            low=Decimal("149.0"),
            close=Decimal("153.0"),
            volume=1000000,
        )
        assert bar.validate_ohlc() is True
        assert bar.symbol == "AAPL"

    def test_invalid_high(self) -> None:
        bar = OHLCVBar(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            open=Decimal("150.0"),
            high=Decimal("148.0"),  # High < open
            low=Decimal("149.0"),
            close=Decimal("153.0"),
            volume=1000000,
        )
        assert bar.validate_ohlc() is False

    def test_invalid_low(self) -> None:
        bar = OHLCVBar(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            open=Decimal("150.0"),
            high=Decimal("155.0"),
            low=Decimal("156.0"),  # Low > open
            close=Decimal("153.0"),
            volume=1000000,
        )
        assert bar.validate_ohlc() is False

    def test_timezone_aware_timestamp(self) -> None:
        bar = OHLCVBar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 14, 30, tzinfo=UTC),
            open=Decimal("150.0"),
            high=Decimal("155.0"),
            low=Decimal("149.0"),
            close=Decimal("153.0"),
            volume=1000000,
        )
        assert bar.timestamp.tzinfo is not None

    def test_symbol_normalization(self) -> None:
        bar = OHLCVBar(
            symbol="aapl",
            timestamp=datetime.now(UTC),
            open=Decimal("150.0"),
            high=Decimal("155.0"),
            low=Decimal("149.0"),
            close=Decimal("153.0"),
            volume=1000000,
        )
        # Note: symbol is not auto-normalized in model, but we can test it accepts lowercase
        assert bar.symbol == "aapl"


class TestQuoteSnapshot:
    def test_valid_quote(self) -> None:
        quote = QuoteSnapshot(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            bid_price=Decimal("150.0"),
            ask_price=Decimal("150.1"),
            bid_size=100,
            ask_size=200,
        )
        assert quote.spread == Decimal("0.1")
        assert quote.midpoint == Decimal("150.05")
        assert quote.is_valid() is True

    def test_invalid_spread(self) -> None:
        quote = QuoteSnapshot(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            bid_price=Decimal("150.1"),
            ask_price=Decimal("150.0"),  # Ask < bid
        )
        assert quote.is_valid() is False


class TestTradeSnapshot:
    def test_trade_snapshot(self) -> None:
        trade = TradeSnapshot(
            symbol="AAPL",
            timestamp=datetime.now(UTC),
            price=Decimal("150.05"),
            size=100,
        )
        assert trade.price == Decimal("150.05")
        assert trade.size == 100


class TestMarketSnapshot:
    def test_snapshot_with_all_components(self) -> None:
        now = datetime.now(UTC)
        quote = QuoteSnapshot(symbol="AAPL", timestamp=now, bid_price=Decimal("150.0"), ask_price=Decimal("150.1"))
        trade = TradeSnapshot(symbol="AAPL", timestamp=now, price=Decimal("150.05"))
        daily_bar = OHLCVBar(
            symbol="AAPL", timestamp=now, open=Decimal("149.0"), high=Decimal("151.0"),
            low=Decimal("148.0"), close=Decimal("150.0"), volume=1000000
        )

        snapshot = MarketSnapshot(
            symbol="AAPL",
            quote=quote,
            trade=trade,
            daily_bar=daily_bar,
        )
        assert snapshot.quote is not None
        assert snapshot.trade is not None
        assert snapshot.daily_bar is not None


class TestTechnicalFeatures:
    def test_features_default_values(self) -> None:
        features = TechnicalFeatures()
        assert features.trend_short == Trend.UNKNOWN
        assert features.trend_medium == Trend.UNKNOWN
        assert features.rsi_14 is None


class TestDataQuality:
    def test_good_quality(self) -> None:
        dq = DataQuality(
            status=DataQualityStatus.GOOD,
            bars_requested=100,
            bars_received=100,
        )
        assert dq.status == DataQualityStatus.GOOD

    def test_insufficient_quality(self) -> None:
        dq = DataQuality(
            status=DataQualityStatus.INSUFFICIENT,
            bars_requested=100,
            bars_received=10,
        )
        assert dq.status == DataQualityStatus.INSUFFICIENT


class TestMarketState:
    def test_market_state_creation(self) -> None:
        now = datetime.now(UTC)
        features = TechnicalFeatures()
        dq = DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100)
        snapshot = MarketSnapshot(symbol="AAPL")

        state = MarketState(
            symbol="AAPL",
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=snapshot,
            features=features,
            data_quality=dq,
        )
        assert state.symbol == "AAPL"
        assert state.timeframe == Timeframe.DAY
        assert state.bars_used == 0


class TestTrend:
    def test_trend_values(self) -> None:
        assert Trend.STRONG_UP == "STRONG_UP"
        assert Trend.UP == "UP"
        assert Trend.NEUTRAL == "NEUTRAL"
        assert Trend.DOWN == "DOWN"
        assert Trend.STRONG_DOWN == "STRONG_DOWN"
        assert Trend.UNKNOWN == "UNKNOWN"


class TestTimeframe:
    def test_timeframe_values(self) -> None:
        assert Timeframe.DAY == "1Day"
        assert Timeframe.HOUR == "1Hour"