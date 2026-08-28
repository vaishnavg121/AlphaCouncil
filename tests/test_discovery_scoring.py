from __future__ import annotations

"""Tests for opportunity scoring."""

from datetime import UTC, datetime
from decimal import Decimal

from app.core.config import Settings
from app.discovery.models import (
    OpportunityScore,
    PreliminaryCandidate,
    ScreeningObservation,
    SignalDirection,
)
from app.discovery.scoring import (
    compute_opportunity_score,
    rank_candidates,
    select_top_k,
)


class TestComputeOpportunityScore:
    def test_score_computation(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        obs = ScreeningObservation(
            symbol="TEST",
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

        score = compute_opportunity_score(obs, settings)

        assert isinstance(score, OpportunityScore)
        assert 0 <= float(score.total) <= 100
        assert score.direction in SignalDirection
        assert isinstance(score.reasons, tuple)
        assert len(score.reasons) > 0

    def test_viable_score(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("0.10"),  # Strong momentum
            return_20d=Decimal("0.20"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("3000000"),  # High volume
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("5.0"),
            distance_sma50_pct=Decimal("10.0"),
            rsi_14=Decimal("55"),
            trend_short="UP",
            trend_medium="UP",
            dollar_volume=Decimal("100_000_000"),
            data_quality_status="GOOD",
            bars_received=100,
        )

        score = compute_opportunity_score(obs, settings)
        assert score.is_viable is True

    def test_non_viable_score(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        obs = ScreeningObservation(
            symbol="TEST",
            as_of=datetime.now(UTC),
            price=Decimal("100"),
            return_5d=Decimal("-0.10"),
            return_20d=Decimal("-0.20"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("100000"),
            realized_vol_20=Decimal("0.80"),  # Extreme vol
            distance_sma20_pct=Decimal("-10.0"),
            distance_sma50_pct=Decimal("-20.0"),
            rsi_14=Decimal("80"),
            trend_short="STRONG_DOWN",
            trend_medium="DOWN",
            dollar_volume=Decimal("1_000_000"),
            data_quality_status="DEGRADED",
            bars_received=30,
        )

        score = compute_opportunity_score(obs, settings)
        assert score.is_viable is False


class TestRankCandidates:
    def test_ranking_by_score(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        def make_candidate(symbol: str, total: float) -> PreliminaryCandidate:
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
                total=Decimal(str(total)),
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
            make_candidate("LOW", 30.0),
            make_candidate("HIGH", 80.0),
            make_candidate("MED", 50.0),
        ]

        ranked = rank_candidates(candidates)
        assert ranked[0].symbol == "HIGH"
        assert ranked[1].symbol == "MED"
        assert ranked[2].symbol == "LOW"

    def test_tie_breaking_by_symbol(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

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

        candidates = [
            make_candidate("ZZZ"),
            make_candidate("AAA"),
            make_candidate("MMM"),
        ]

        ranked = rank_candidates(candidates, tie_breaker="symbol")
        assert ranked[0].symbol == "AAA"
        assert ranked[1].symbol == "MMM"
        assert ranked[2].symbol == "ZZZ"


class TestSelectTopK:
    def test_select_top_k(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        def make_candidate(symbol: str, total: float) -> PreliminaryCandidate:
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
                total=Decimal(str(total)),
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
            make_candidate("A", 80.0),
            make_candidate("B", 70.0),
            make_candidate("C", 60.0),
            make_candidate("D", 50.0),
            make_candidate("E", 40.0),
        ]

        top_k = select_top_k(candidates, 3)
        assert len(top_k) == 3
        assert top_k[0].symbol == "A"
        assert top_k[1].symbol == "B"
        assert top_k[2].symbol == "C"

    def test_select_top_k_exceeds_length(self) -> None:
        settings = Settings.model_construct(
            discovery_weight_momentum=0.20,
            discovery_weight_trend=0.20,
            discovery_weight_volume=0.15,
            discovery_weight_volatility=0.15,
            discovery_weight_mean_reversion=0.10,
            discovery_weight_liquidity=0.10,
            discovery_weight_quality=0.10,
        )

        def make_candidate(symbol: str, total: float) -> PreliminaryCandidate:
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
                total=Decimal(str(total)),
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

        candidates = [make_candidate("A", 80.0), make_candidate("B", 70.0)]
        top_k = select_top_k(candidates, 5)
        assert len(top_k) == 2