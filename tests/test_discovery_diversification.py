from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

from app.discovery.diversification import (
    apply_directional_balance,
    apply_diversification,
    apply_final_diversification,
)
from app.discovery.models import (
    OpportunityScore,
    PreliminaryCandidate,
    ScreeningObservation,
    SignalDirection,
)
from app.discovery.universe import CuratedUniverseProvider
from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    TechnicalFeatures,
    Timeframe,
)


class TestApplyDiversification:
    def test_category_cap(self) -> None:
        provider = CuratedUniverseProvider()

        def make_candidate(symbol: str) -> PreliminaryCandidate:
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
                total=Decimal("60.0"),
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

        # Create many ETFs and EQUITIES
        candidates = [
            make_candidate("SPY"),   # ETF
            make_candidate("QQQ"),   # ETF
            make_candidate("IWM"),   # ETF
            make_candidate("DIA"),   # ETF
            make_candidate("VTI"),   # ETF
            make_candidate("AAPL"),  # EQUITY
            make_candidate("MSFT"),  # EQUITY
            make_candidate("GOOGL"), # EQUITY
        ]

        # Max 3 per category
        diversified = apply_diversification(
            candidates, CuratedUniverseProvider(), max_per_group=3
        )

        # Should have at most 3 ETFs and 3 EQUITIES
        etf_count = sum(1 for c in diversified if CuratedUniverseProvider().get_asset_category(c.symbol) == "ETF")
        equity_count = sum(1 for c in diversified if CuratedUniverseProvider().get_asset_category(c.symbol) == "EQUITY")

        assert etf_count <= 3
        assert equity_count <= 3
        assert len(diversified) <= 6

    def test_preserves_rank_order(self) -> None:
        provider = CuratedUniverseProvider()

        def make_candidate(symbol: str, rank: int) -> PreliminaryCandidate:
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
                total=Decimal(str(100 - rank)),  # Higher rank = better score
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

        candidates = [
            make_candidate("AAPL", 1),
            make_candidate("MSFT", 2),
            make_candidate("GOOGL", 3),
            make_candidate("SPY", 4),  # ETF
            make_candidate("QQQ", 5),  # ETF
        ]

        diversified = apply_diversification(candidates, provider, max_per_group=2)

        # AAPL and MSFT should be kept (rank 1, 2)
        # GOOGL should be dropped (rank 3, EQUITY cap at 2)
        # SPY and QQQ should be kept (ETF cap at 2)
        kept_symbols = {c.symbol for c in diversified}
        assert "AAPL" in kept_symbols
        assert "MSFT" in kept_symbols
        assert "GOOGL" not in kept_symbols
        assert "SPY" in kept_symbols
        assert "QQQ" in kept_symbols


class TestApplyDirectionalBalance:
    def test_no_balance_required(self) -> None:
        candidates = [Mock(), Mock()]
        result = apply_directional_balance(candidates, min_bullish=0, min_bearish=0)
        assert result == candidates

    def test_bullish_requirement(self) -> None:
        bullish = Mock()
        bullish.score.direction = SignalDirection.BULLISH
        bearish = Mock()
        bearish.score.direction = SignalDirection.BEARISH
        neutral = Mock()
        neutral.score.direction = SignalDirection.NEUTRAL

        candidates = [bullish, bearish, neutral]
        result = apply_directional_balance(candidates, min_bullish=1, min_bearish=1)

        assert len(result) == 3
        assert bullish in result
        assert bearish in result


class TestApplyFinalDiversification:
    def test_final_diversification(self) -> None:
        from datetime import datetime

        from app.discovery.models import Candidate, OpportunityScore

        def make_candidate(symbol: str) -> Candidate:
            market_state = MarketState(
                symbol=symbol,
                as_of=datetime.now(UTC),
                timeframe=Timeframe.DAY,
                snapshot=MarketSnapshot(symbol=symbol),
                features=TechnicalFeatures(),
                data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
            )
            score = OpportunityScore(
                total=Decimal("60.0"),
                momentum=Decimal("50"),
                trend=Decimal("50"),
                volume=Decimal("50"),
                volatility=Decimal("50"),
                mean_reversion=Decimal("50"),
                liquidity=Decimal("50"),
                quality=Decimal("50"),
                direction=SignalDirection.NEUTRAL,
            )
            return Candidate(
                symbol=symbol,
                rank=1,
                direction=SignalDirection.NEUTRAL,
                opportunity_score=score,
                market_state=market_state,
            )

        candidates = [
            make_candidate("SPY"),   # ETF
            make_candidate("QQQ"),   # ETF
            make_candidate("IWM"),   # ETF
            make_candidate("AAPL"),  # EQUITY
            make_candidate("MSFT"),  # EQUITY
            make_candidate("GOOGL"), # EQUITY
        ]

        diversified = apply_final_diversification(
            candidates, CuratedUniverseProvider(), max_per_group=2
        )

        etf_count = sum(1 for c in diversified if CuratedUniverseProvider().get_asset_category(c.symbol) == "ETF")
        equity_count = sum(1 for c in diversified if CuratedUniverseProvider().get_asset_category(c.symbol) == "EQUITY")

        assert etf_count <= 2
        assert equity_count <= 2
        assert len(diversified) <= 4