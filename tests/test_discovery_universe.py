from __future__ import annotations

"""Tests for universe providers."""


from unittest.mock import Mock

import pytest

from app.discovery.universe import (
    AlpacaUniverseProvider,
    CuratedUniverseProvider,
    create_universe_provider,
)
from app.market.gateway import MarketDataGateway


class TestCuratedUniverseProvider:
    def test_default_universe(self) -> None:
        provider = CuratedUniverseProvider()
        universe = provider.get_universe("curated")

        assert len(universe) > 0
        assert "AAPL" in universe
        assert "SPY" in universe
        assert "MSFT" in universe

    def test_custom_universe(self) -> None:
        custom = ("AAPL", "MSFT", "GOOGL")
        provider = CuratedUniverseProvider(universe=custom)
        universe = provider.get_universe("curated")

        assert universe == ["AAPL", "MSFT", "GOOGL"]

    def test_asset_category_etf(self) -> None:
        provider = CuratedUniverseProvider()
        assert provider.get_asset_category("SPY") == "ETF"
        assert provider.get_asset_category("QQQ") == "ETF"

    def test_asset_category_equity(self) -> None:
        provider = CuratedUniverseProvider()
        assert provider.get_asset_category("AAPL") == "EQUITY"
        assert provider.get_asset_category("MSFT") == "EQUITY"

    def test_unknown_mode_raises(self) -> None:
        provider = CuratedUniverseProvider()
        with pytest.raises(ValueError):
            provider.get_universe("alpaca")


class TestAlpacaUniverseProvider:
    def test_requires_gateway(self) -> None:
        with pytest.raises(ValueError):
            AlpacaUniverseProvider(gateway=None)

    def test_get_universe_without_trading_client(self) -> None:
        gateway = Mock(spec=MarketDataGateway)
        gateway._trading_client = None

        provider = AlpacaUniverseProvider(gateway=gateway)
        universe = provider.get_universe("alpaca")

        assert universe == []

    def test_asset_category_caching(self) -> None:
        gateway = Mock(spec=MarketDataGateway)
        gateway._trading_client = None

        provider = AlpacaUniverseProvider(gateway=gateway)
        cat1 = provider.get_asset_category("AAPL")
        cat2 = provider.get_asset_category("AAPL")

        assert cat1 == cat2 == "EQUITY"


class TestCreateUniverseProvider:
    def test_create_curated(self) -> None:
        provider = create_universe_provider("curated")
        assert isinstance(provider, CuratedUniverseProvider)

    def test_create_alpaca_requires_gateway(self) -> None:
        with pytest.raises(ValueError):
            create_universe_provider("alpaca", gateway=None)

    def test_create_alpaca_with_gateway(self) -> None:
        gateway = Mock(spec=MarketDataGateway)
        provider = create_universe_provider("alpaca", gateway=gateway)
        assert isinstance(provider, AlpacaUniverseProvider)

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError):
            create_universe_provider("invalid")