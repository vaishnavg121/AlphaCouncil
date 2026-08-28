from __future__ import annotations

from datetime import UTC, datetime

"""Tests for discovery domain models."""


from decimal import Decimal

from app.discovery.models import (
    AssetCategory,
    Candidate,
    CandidateRejection,
    CandidateSet,
    OpportunityScore,
    PreliminaryCandidate,
    RejectionReason,
    ScreeningObservation,
    SignalDirection,
    UniverseMode,
)


class TestScreeningObservation:
    def test_valid_observation(self) -> None:
        obs = ScreeningObservation(
            symbol="AAPL",
            as_of=datetime.now(UTC),
            price=Decimal("150.0"),
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("1200000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.5"),
            rsi_14=Decimal("55"),
        )
        assert obs.symbol == "AAPL"
        assert obs.has_sufficient_data is True

    def test_insufficient_data(self) -> None:
        obs = ScreeningObservation(
            symbol="AAPL",
            as_of=datetime.now(UTC),
            price=Decimal("150.0"),
        )
        assert obs.has_sufficient_data is False


class TestOpportunityScore:
    def test_score_creation(self) -> None:
        score = OpportunityScore(
            total=Decimal("75.5"),
            momentum=Decimal("80"),
            trend=Decimal("70"),
            volume=Decimal("60"),
            volatility=Decimal("75"),
            mean_reversion=Decimal("50"),
            liquidity=Decimal("90"),
            quality=Decimal("100"),
            direction=SignalDirection.BULLISH,
        )
        assert score.total == Decimal("75.5")
        assert score.direction == SignalDirection.BULLISH
        assert score.is_viable is True

    def test_low_score_not_viable(self) -> None:
        score = OpportunityScore(
            total=Decimal("25.0"),
            momentum=Decimal("30"),
            trend=Decimal("30"),
            volume=Decimal("30"),
            volatility=Decimal("30"),
            mean_reversion=Decimal("30"),
            liquidity=Decimal("30"),
            quality=Decimal("30"),
            direction=SignalDirection.NEUTRAL,
        )
        assert score.is_viable is False


class TestPreliminaryCandidate:
    def test_preliminary_candidate(self) -> None:
        obs = ScreeningObservation(
            symbol="AAPL",
            as_of=datetime.now(UTC),
            price=Decimal("150.0"),
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("1200000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.5"),
            rsi_14=Decimal("55"),
        )
        score = OpportunityScore(
            total=Decimal("75.5"),
            momentum=Decimal("80"),
            trend=Decimal("70"),
            volume=Decimal("60"),
            volatility=Decimal("75"),
            mean_reversion=Decimal("50"),
            liquidity=Decimal("90"),
            quality=Decimal("100"),
            direction=SignalDirection.BULLISH,
        )
        candidate = PreliminaryCandidate(
            symbol="AAPL",
            observation=obs,
            score=score,
        )
        assert candidate.symbol == "AAPL"
        assert candidate.score.total == Decimal("75.5")


class TestCandidate:
    def test_candidate_creation(self) -> None:
        from app.market.models import (
            DataQuality,
            DataQualityStatus,
            MarketSnapshot,
            MarketState,
            TechnicalFeatures,
            Timeframe,
        )

        market_state = MarketState(
            symbol="AAPL",
            as_of=datetime.now(UTC),
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(symbol="AAPL"),
            features=TechnicalFeatures(),
            data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
        )

        score = OpportunityScore(
            total=Decimal("75.5"),
            momentum=Decimal("80"),
            trend=Decimal("70"),
            volume=Decimal("60"),
            volatility=Decimal("75"),
            mean_reversion=Decimal("50"),
            liquidity=Decimal("90"),
            quality=Decimal("100"),
            direction=SignalDirection.BULLISH,
        )

        candidate = Candidate(
            symbol="AAPL",
            rank=1,
            direction=SignalDirection.BULLISH,
            opportunity_score=score,
            market_state=market_state,
        )
        assert candidate.rank == 1
        assert candidate.symbol == "AAPL"


class TestCandidateRejection:
    def test_rejection_creation(self) -> None:
        rejection = CandidateRejection(
            symbol="INVALID",
            reason=RejectionReason.NOT_TRADABLE,
            message="Asset not tradable",
        )
        assert rejection.symbol == "INVALID"
        assert rejection.reason == RejectionReason.NOT_TRADABLE


class TestCandidateSet:
    def test_candidate_set(self) -> None:
        from app.market.models import (
            DataQuality,
            DataQualityStatus,
            MarketSnapshot,
            MarketState,
            TechnicalFeatures,
            Timeframe,
        )

        market_state = MarketState(
            symbol="AAPL",
            as_of=datetime.now(UTC),
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(symbol="AAPL"),
            features=TechnicalFeatures(),
            data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
        )

        score = OpportunityScore(
            total=Decimal("75.5"),
            momentum=Decimal("80"),
            trend=Decimal("70"),
            volume=Decimal("60"),
            volatility=Decimal("75"),
            mean_reversion=Decimal("50"),
            liquidity=Decimal("90"),
            quality=Decimal("100"),
            direction=SignalDirection.BULLISH,
        )

        candidate = Candidate(
            symbol="AAPL",
            rank=1,
            direction=SignalDirection.BULLISH,
            opportunity_score=score,
            market_state=market_state,
        )

        cset = CandidateSet(
            generated_at=datetime.now(UTC),
            universe_mode=UniverseMode.CURATED,
            universe_size=50,
            eligible_count=45,
            rejected_count=5,
            preliminary_count=30,
            deep_analysis_count=15,
            final_count=5,
            candidates=(candidate,),
        )
        assert cset.final_count == 5
        assert len(cset.candidates) == 1


class TestEnums:
    def test_universe_mode(self) -> None:
        assert UniverseMode.CURATED == "curated"
        assert UniverseMode.ALPACA == "alpaca"

    def test_signal_direction(self) -> None:
        assert SignalDirection.BULLISH == "BULLISH"
        assert SignalDirection.BEARISH == "BEARISH"
        assert SignalDirection.MIXED == "MIXED"
        assert SignalDirection.NEUTRAL == "NEUTRAL"

    def test_rejection_reason(self) -> None:
        assert RejectionReason.NOT_TRADABLE == "NOT_TRADABLE"
        assert RejectionReason.PRICE_TOO_LOW == "PRICE_TOO_LOW"
        assert RejectionReason.LOW_LIQUIDITY == "LOW_LIQUIDITY"

    def test_asset_category(self) -> None:
        assert AssetCategory.EQUITY == "EQUITY"
        assert AssetCategory.ETF == "ETF"