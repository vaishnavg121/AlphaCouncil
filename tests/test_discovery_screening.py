from __future__ import annotations

from datetime import UTC, datetime, timedelta

"""Tests for bulk screening."""


from decimal import Decimal
from unittest.mock import Mock

from app.core.config import Settings
from app.discovery.screening import BulkScreener
from app.market.gateway import MarketDataError, MarketDataGateway
from app.market.models import OHLCVBar, Timeframe


class TestBulkScreener:
    def setup_method(self) -> None:
        self.gateway = Mock(spec=MarketDataGateway)
        self.settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )
        self.screener = BulkScreener(self.gateway, self.settings)

    def test_screen_symbols_success(self) -> None:
        # Mock bars and snapshot
        bars = []
        base_time = datetime.now(UTC) - timedelta(days=50)
        for i in range(50):
            bars.append(OHLCVBar(
                symbol="AAPL",
                timestamp=base_time + timedelta(days=i),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000000,
            ))

        self.gateway.get_bars.return_value = bars
        self.gateway.get_snapshot.return_value = Mock(
            trade=Mock(price=Decimal("100"), size=100),
            quote=Mock(bid_price=Decimal("99.99"), ask_price=Decimal("100.01"), is_valid=Mock(return_value=True)),
            daily_bar=None,
            previous_daily_bar=None,
        )

        observations = self.screener.screen_symbols(["AAPL", "MSFT"])

        assert len(observations) == 2
        assert observations[0].symbol == "AAPL"
        assert observations[1].symbol == "MSFT"
        assert observations[0].price == Decimal("100")
        assert observations[0].data_quality_status == "GOOD"

    def test_screen_symbols_market_data_error(self) -> None:
        self.gateway.get_bars.side_effect = MarketDataError("API error")

        observations = self.screener.screen_symbols(["ERROR"])

        assert len(observations) == 1
        assert observations[0].symbol == "ERROR"
        assert observations[0].data_quality_status == "PROVIDER_ERROR"
        assert observations[0].price == Decimal("0")

    def test_screen_symbols_generic_error(self) -> None:
        self.gateway.get_bars.side_effect = Exception("Unexpected")

        observations = self.screener.screen_symbols(["ERROR"])

        assert len(observations) == 1
        assert observations[0].symbol == "ERROR"
        assert observations[0].data_quality_status == "INVALID_DATA"

    def test_screen_single_insufficient_bars(self) -> None:
        self.gateway.get_bars.return_value = []  # No bars

        obs = self.screener._screen_single("EMPTY", Timeframe.DAY)

        assert obs.symbol == "EMPTY"
        assert obs.data_quality_status == "INSUFFICIENT"
        assert obs.bars_received == 0

    def test_screen_single_few_bars(self) -> None:
        bars = [OHLCVBar(
            symbol="FEW",
            timestamp=datetime.now(UTC) - timedelta(days=i),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=1000000,
        ) for i in range(10)]  # Less than 20

        self.gateway.get_bars.return_value = bars
        self.gateway.get_snapshot.return_value = Mock(
            trade=Mock(price=Decimal("100"), size=100),
            quote=Mock(bid_price=Decimal("99.99"), ask_price=Decimal("100.01"), is_valid=Mock(return_value=True)),
            daily_bar=None,
            previous_daily_bar=None,
        )

        obs = self.screener._screen_single("FEW", Timeframe.DAY)

        assert obs.symbol == "FEW"
        assert obs.bars_received == 10
        assert obs.data_quality_status == "INSUFFICIENT"