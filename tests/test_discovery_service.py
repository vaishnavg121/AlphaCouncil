from __future__ import annotations

from datetime import UTC, datetime

"""Tests for the discovery service orchestration."""


from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.discovery.models import (
    CandidateSet,
    OpportunityScore,
    PreliminaryCandidate,
    ScreeningObservation,
    SignalDirection,
)
from app.discovery.service import OpportunityDiscoveryService, create_discovery_service
from app.discovery.universe import CuratedUniverseProvider
from app.market.gateway import MarketDataGateway
from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    TechnicalFeatures,
    Timeframe,
)


class TestCreateDiscoveryService:
    def test_factory_function(self) -> None:
        gateway = Mock(spec=MarketDataGateway)
        service = create_discovery_service(gateway)
        assert isinstance(service, OpportunityDiscoveryService)


class TestOpportunityDiscoveryService:
    def setup_method(self) -> None:
        self.gateway = Mock(spec=MarketDataGateway)
        self.gateway._trading_client = None
        self.settings = Settings.model_construct(
            discovery_universe_mode="curated",
            discovery_preliminary_k=20,
            discovery_deep_analysis_k=15,
            discovery_final_k=10,
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
            discovery_max_per_group=3,
            discovery_deep_concurrency=3,
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )
        self.service = OpportunityDiscoveryService(
            self.gateway,
            self.settings,
            universe_provider=CuratedUniverseProvider(),
        )

    def test_discover_with_curated_universe(self) -> None:
        # Mock the screener
        with patch.object(self.service, '_screener') as mock_screener:
            mock_obs = ScreeningObservation(
                symbol="AAPL",
                as_of=datetime.now(UTC),
                price=Decimal("150"),
                return_5d=Decimal("0.05"),
                return_20d=Decimal("0.10"),
                avg_volume_20=Decimal("1000000"),
                volume=Decimal("2000000"),
                realized_vol_20=Decimal("0.25"),
                distance_sma20_pct=Decimal("5.0"),
                distance_sma50_pct=Decimal("10.0"),
                rsi_14=Decimal("55"),
                trend_short="UP",
                trend_medium="UP",
                dollar_volume=Decimal("50_000_000"),
                data_quality_status="GOOD",
                bars_received=100,
            )
            mock_screener.screen_symbols.return_value = [mock_obs]

            # Mock state builder
            with patch.object(self.service, '_state_builder') as mock_builder:
                mock_state = MarketState(
                    symbol="AAPL",
                    as_of=datetime.now(UTC),
                    timeframe=Timeframe.DAY,
                    snapshot=MarketSnapshot(symbol="AAPL"),
                    features=TechnicalFeatures(),
                    data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
                )
                mock_builder.build.return_value = mock_state

                result = self.service.discover()

                assert isinstance(result, CandidateSet)
                # Basic checks
                assert result.universe_size > 0
                assert result.runtime_ms >= 0

    def test_discover_respects_final_k(self) -> None:
        settings = Settings.model_construct(
            discovery_universe_mode="curated",
            discovery_preliminary_k=20,
            discovery_deep_analysis_k=15,
            discovery_final_k=3,  # Only 3 final
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
            discovery_max_per_group=3,
            discovery_deep_concurrency=3,
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        service = OpportunityDiscoveryService(
            self.gateway,
            settings,
            universe_provider=CuratedUniverseProvider(),
        )

        # Mock screener to return many viable candidates
        with patch.object(service, '_screener') as mock_screener:
            obs_list = []
            for sym in ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "NFLX", "AMD", "INTC"]:
                obs = ScreeningObservation(
                    symbol=sym,
                    as_of=datetime.now(UTC),
                    price=Decimal("100"),
                    return_5d=Decimal("0.05"),
                    return_20d=Decimal("0.10"),
                    avg_volume_20=Decimal("1000000"),
                    volume=Decimal("2000000"),
                    realized_vol_20=Decimal("0.25"),
                    distance_sma20_pct=Decimal("5.0"),
                    distance_sma50_pct=Decimal("10.0"),
                    rsi_14=Decimal("55"),
                    trend_short="UP",
                    trend_medium="UP",
                    dollar_volume=Decimal("50_000_000"),
                    data_quality_status="GOOD",
                    bars_received=100,
                )
                obs_list.append(obs)
            mock_screener.screen_symbols.return_value = obs_list

            with patch.object(service, '_state_builder') as mock_builder:
                mock_state = MarketState(
                    symbol="AAPL",
                    as_of=datetime.now(UTC),
                    timeframe=Timeframe.DAY,
                    snapshot=MarketSnapshot(symbol="AAPL"),
                    features=TechnicalFeatures(),
                    data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
                )
                mock_builder.build.return_value = mock_state

                result = service.discover()
                assert result.final_count <= 3

    def test_discover_handles_state_builder_failure(self) -> None:
        with patch.object(self.service, '_screener') as mock_screener:
            mock_obs = ScreeningObservation(
                symbol="AAPL",
                as_of=datetime.now(UTC),
                price=Decimal("150"),
                return_5d=Decimal("0.05"),
                return_20d=Decimal("0.10"),
                avg_volume_20=Decimal("1000000"),
                volume=Decimal("2000000"),
                realized_vol_20=Decimal("0.25"),
                distance_sma20_pct=Decimal("5.0"),
                distance_sma50_pct=Decimal("10.0"),
                rsi_14=Decimal("55"),
                trend_short="UP",
                trend_medium="UP",
                dollar_volume=Decimal("50_000_000"),
                data_quality_status="GOOD",
                bars_received=100,
            )
            mock_screener.screen_symbols.return_value = [mock_obs]

            with patch.object(self.service, '_state_builder') as mock_builder:
                mock_builder.build.side_effect = Exception("API Error")

                result = self.service.discover()
                assert result.deep_analysis_count >= 0
                assert len(result.rejections) > 0
                assert result.rejections[0].reason == "PROVIDER_ERROR"

    def test_discover_universe_mode_override(self) -> None:
        with patch.object(self.service, '_universe_provider') as mock_provider:
            mock_provider.get_universe.return_value = ["AAPL", "MSFT"]

            with patch.object(self.service, '_screener') as mock_screener:
                mock_screener.screen_symbols.return_value = []

                result = self.service.discover(universe_mode="alpaca")
                mock_provider.get_universe.assert_called_with("alpaca")


class TestDiscoverServiceIntegration:
    @pytest.mark.integration
    def test_real_discovery_small_universe(self) -> None:
        """Integration test with real Alpaca gateway (requires credentials)."""
        pytest.skip("Requires live credentials")


def make_preliminary_candidate(symbol: str, score_val: float) -> PreliminaryCandidate:
    """Helper to create a preliminary candidate for testing."""
    obs = ScreeningObservation(
        symbol=symbol,
        as_of=datetime.now(UTC),
        price=Decimal("100"),
        return_5d=Decimal("0.01"),
        return_20d=Decimal("0.02"),
        avg_volume_20=Decimal("1000000"),
        volume=Decimal("1000000"),
        realized_vol_20=Decimal("0.25"),
        distance_sma20_pct=Decimal("1.0"),
        rsi_14=Decimal("50"),
        dollar_volume=Decimal("10_000_000"),
        data_quality_status="GOOD",
        bars_received=100,
    )
    score = OpportunityScore(
        total=Decimal(str(score_val)),
        momentum=Decimal("50"),
        trend=Decimal("50"),
        volume=Decimal("50"),
        volatility=Decimal("50"),
        mean_reversion=Decimal("50"),
        liquidity=Decimal("50"),
        quality=Decimal("50"),
        direction=SignalDirection.NEUTRAL,
    )
    return PreliminaryCandidate(symbol=symbol, observation=obs, score=score)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])