"""Tests for market gateway and state builder."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app.market import AlpacaMarketDataGateway, MarketDataError
from app.market.models import (
    DataQualityStatus,
    MarketSnapshot,
    OHLCVBar,
    QuoteSnapshot,
    Timeframe,
    TradeSnapshot,
)
from app.market.state import InsufficientDataError, MarketStateBuilder


class FakeMarketDataGateway:
    """Fake gateway for testing."""

    def __init__(
        self,
        bars: list[OHLCVBar] | None = None,
        snapshot: MarketSnapshot | None = None,
        should_fail: bool = False,
    ) -> None:
        self._bars = bars or []
        self._snapshot = snapshot
        self._should_fail = should_fail

    def get_latest_quote(self, symbol: str) -> QuoteSnapshot:
        if self._should_fail:
            raise MarketDataError("Quote failed")
        return QuoteSnapshot(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            bid_price=Decimal("150.0"),
            ask_price=Decimal("150.1"),
        )

    def get_latest_trade(self, symbol: str) -> TradeSnapshot:
        if self._should_fail:
            raise MarketDataError("Trade failed")
        return TradeSnapshot(
            symbol=symbol,
            timestamp=datetime.now(UTC),
            price=Decimal("150.05"),
            size=100,
        )

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        if self._should_fail:
            raise MarketDataError("Snapshot failed")
        return self._snapshot or MarketSnapshot(symbol=symbol)

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        if self._should_fail:
            raise MarketDataError("Bars failed")
        return self._bars

    def get_daily_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        return self.get_bars(symbol, Timeframe.DAY, start, end, limit)


class TestMarketStateBuilder:
    def test_build_success(self) -> None:
        # Create sufficient bars (60 bars for SMA50)
        bars = []
        base_price = 150
        for i in range(60):
            price = base_price + i * 0.1
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=60-i),
                open=Decimal(str(price - 0.1)),
                high=Decimal(str(price + 0.2)),
                low=Decimal(str(price - 0.3)),
                close=Decimal(str(price)),
                volume=1000000,
            ))

        snapshot = MarketSnapshot(
            symbol="AAPL",
            trade=TradeSnapshot(
                symbol="AAPL",
                timestamp=datetime.now(UTC),
                price=Decimal("156.0"),
                size=100,
            ),
        )

        gateway = FakeMarketDataGateway(bars=bars, snapshot=snapshot)
        builder = MarketStateBuilder(gateway, default_lookback_days=60)
        state = builder.build("AAPL")

        assert state.symbol == "AAPL"
        assert state.bars_used == 60
        assert state.latest_bar is not None
        assert state.features.sma_20 is not None
        assert state.features.sma_50 is not None
        assert state.data_quality.status == DataQualityStatus.GOOD

    def test_build_insufficient_data(self) -> None:
        # Only 10 bars - insufficient for SMA50
        bars = []
        for i in range(10):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=10-i),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=1000000,
            ))

        gateway = FakeMarketDataGateway(bars=bars)
        builder = MarketStateBuilder(gateway, default_lookback_days=10)

        with pytest.raises(InsufficientDataError) as exc_info:
            builder.build("AAPL")

        assert exc_info.value.bars_received == 10
        assert exc_info.value.bars_required == 50

    def test_build_gateway_failure(self) -> None:
        gateway = FakeMarketDataGateway(should_fail=True)
        builder = MarketStateBuilder(gateway)

        with pytest.raises(MarketDataError):
            builder.build("AAPL")

    def test_build_duplicate_bars_handled(self) -> None:
        bars = []
        base_time = datetime.now(UTC) - timedelta(days=60)
        for i in range(60):
            price = 150 + i * 0.1
            ts = base_time + timedelta(days=i)
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=ts,
                open=Decimal(str(price - 0.1)),
                high=Decimal(str(price + 0.2)),
                low=Decimal(str(price - 0.3)),
                close=Decimal(str(price)),
                volume=1000000,
            ))
        # Add duplicate
        bars.append(bars[-1])

        snapshot = MarketSnapshot(symbol="AAPL")
        gateway = FakeMarketDataGateway(bars=bars, snapshot=snapshot)
        builder = MarketStateBuilder(gateway, default_lookback_days=61)
        state = builder.build("AAPL")

        assert state.data_quality.duplicate_bars == 1
        assert state.data_quality.status == DataQualityStatus.DEGRADED

    def test_build_invalid_ohlc_handled(self) -> None:
        bars = []
        base_time = datetime.now(UTC) - timedelta(days=60)
        for i in range(60):
            price = 150 + i * 0.1
            ts = base_time + timedelta(days=i)
            # Make one bar invalid
            if i == 30:
                bars.append(OHLCVBar(
                    symbol="AAPL",
                    timestamp=ts,
                    open=Decimal(str(price - 0.1)),
                    high=Decimal(str(price - 0.5)),  # Invalid: high < open
                    low=Decimal(str(price - 0.3)),
                    close=Decimal(str(price)),
                    volume=1000000,
                ))
            else:
                bars.append(OHLCVBar(
                    symbol="AAPL",
                    timestamp=ts,
                    open=Decimal(str(price - 0.1)),
                    high=Decimal(str(price + 0.2)),
                    low=Decimal(str(price - 0.3)),
                    close=Decimal(str(price)),
                    volume=1000000,
                ))

        snapshot = MarketSnapshot(symbol="AAPL")
        gateway = FakeMarketDataGateway(bars=bars, snapshot=snapshot)
        builder = MarketStateBuilder(gateway, default_lookback_days=60)
        state = builder.build("AAPL")

        assert state.data_quality.missing_values == 1
        assert state.data_quality.status == DataQualityStatus.DEGRADED

    def test_build_symbol_normalization(self) -> None:
        bars = []
        for i in range(60):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=60-i),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=1000000,
            ))

        gateway = FakeMarketDataGateway(bars=bars)
        builder = MarketStateBuilder(gateway, default_lookback_days=60)
        state = builder.build("aapl")  # lowercase

        assert state.symbol == "AAPL"

    def test_data_quality_warnings(self) -> None:
        # Enough bars for features but few relative to lookback
        bars = []
        for i in range(60):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=datetime.now(UTC) - timedelta(days=60-i),
                open=Decimal("150"),
                high=Decimal("151"),
                low=Decimal("149"),
                close=Decimal("150"),
                volume=1000000,
            ))

        snapshot = MarketSnapshot(symbol="AAPL")
        gateway = FakeMarketDataGateway(bars=bars, snapshot=snapshot)
        builder = MarketStateBuilder(gateway, default_lookback_days=150)
        state = builder.build("AAPL")

        # Should have warning about possible missing bars
        assert len(state.data_quality.warnings) > 0
        assert any("missing bars" in w.lower() for w in state.data_quality.warnings)


class TestMarketDataGatewayProtocol:
    def test_gateway_methods_exist(self) -> None:
        gateway = FakeMarketDataGateway()
        assert hasattr(gateway, "get_latest_quote")
        assert hasattr(gateway, "get_latest_trade")
        assert hasattr(gateway, "get_snapshot")
        assert hasattr(gateway, "get_bars")
        assert hasattr(gateway, "get_daily_bars")


class TestAlpacaMarketDataGatewayConstruction:
    def test_from_settings_requires_credentials(self) -> None:
        """Test that gateway construction validates credentials properly.
        
        This test verifies the validation logic by mocking the credentials provider
        to return unavailable credentials.
        """
        from app.alpaca.auth import AlpacaAuthType, AlpacaCredentials
        from app.core.config import Settings
        
        settings = Settings.model_construct(
            alpaca_data_feed="iex",
            alpaca_api_key=None,
            alpaca_secret_key=None,
            nvidia_api_key=None,
            llm_model="test",
        )
        
        # Mock the credentials provider to return unavailable credentials
        with patch('app.market.alpaca_gateway.AlpacaCredentialsProvider') as mock_provider_class:
            mock_provider = Mock()
            mock_provider.resolve.return_value = AlpacaCredentials(auth_type=AlpacaAuthType.UNAVAILABLE)
            mock_provider_class.return_value = mock_provider
            
            with pytest.raises(Exception) as exc_info:
                AlpacaMarketDataGateway.from_settings(settings)
            assert "credential" in str(exc_info.value).lower() or "unavailable" in str(exc_info.value).lower()