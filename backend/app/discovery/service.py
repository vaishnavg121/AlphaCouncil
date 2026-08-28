"""Main discovery service orchestrating the M2 pipeline.

Two-stage funnel:
1. Cheap screening of universe -> preliminary candidates
2. Deep M1 analysis of top-K -> final candidates
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.core.config import Settings
from app.discovery.diversification import apply_diversification, apply_final_diversification
from app.discovery.filters import apply_hard_filters
from app.discovery.models import (
    Candidate,
    CandidateRejection,
    CandidateSet,
    PreliminaryCandidate,
    UniverseMode,
    RejectionReason,
)
from app.discovery.scoring import compute_opportunity_score, rank_candidates, select_top_k
from app.discovery.screening import BulkScreener
from app.discovery.universe import UniverseProvider, create_universe_provider
from app.market import MarketStateBuilder
from app.market.gateway import MarketDataGateway
from app.market.models import MarketState


class OpportunityDiscoveryService:
    """Orchestrates the complete opportunity discovery pipeline."""

    def __init__(
        self,
        gateway: MarketDataGateway,
        settings: Settings | None = None,
        universe_provider: UniverseProvider | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings or Settings()
        self._universe_provider = universe_provider or create_universe_provider(
            self._settings.discovery_universe_mode,
            gateway,
            self._settings,
        )
        self._screener = BulkScreener(gateway, self._settings)
        self._state_builder = MarketStateBuilder(gateway, self._settings)

    def discover(
        self,
        universe_mode: Literal["curated", "alpaca"] | None = None,
        final_k: int | None = None,
    ) -> CandidateSet:
        """Run the complete discovery pipeline.

        Args:
            universe_mode: Override universe mode (curated/alpaca).
            final_k: Override final candidate count.

        Returns:
            CandidateSet with ranked candidates and metadata.
        """
        start_time = datetime.now(UTC)
        mode = universe_mode or self._settings.discovery_universe_mode
        final_k = final_k or self._settings.discovery_final_k

        # Stage 0: Get universe
        symbols = self._universe_provider.get_universe(mode)
        universe_size = len(symbols)

        # Stage 1: Bulk screening
        observations = self._screener.screen_symbols(symbols)

        # Stage 2: Hard filters
        eligible_obs, filter_rejections = apply_hard_filters(observations, self._settings)

        # Stage 3: Compute scores for eligible
        preliminary_candidates = []
        for obs in eligible_obs:
            score = compute_opportunity_score(obs, self._settings)
            if score.is_viable:
                preliminary_candidates.append(
                    PreliminaryCandidate(
                        symbol=obs.symbol,
                        observation=obs,
                        score=score,
                    )
                )

        # Stage 4: Preliminary ranking
        ranked = rank_candidates(preliminary_candidates)
        preliminary_count = len(ranked)

        # Stage 5: Diversification on preliminary
        diversified = apply_diversification(
            ranked,
            self._universe_provider,
            max_per_group=self._settings.discovery_max_per_group,
        )

        # Stage 6: Select top-K for deep analysis
        deep_k = min(self._settings.discovery_deep_analysis_k, len(diversified))
        deep_candidates = select_top_k(diversified, deep_k)

        # Stage 7: Deep M1 analysis
        final_candidates: list[Candidate] = []
        deep_rejections: list[CandidateRejection] = []
        for prelim in deep_candidates:
            try:
                market_state = self._state_builder.build(prelim.symbol)
                # Recompute score with full market state validation
                # (could add deep validation here)
                candidate = self._build_final_candidate(
                    prelim, market_state, len(final_candidates) + 1
                )
                final_candidates.append(candidate)
            except Exception as e:
                deep_rejections.append(
                    CandidateRejection(
                        symbol=prelim.symbol,
                        reason=RejectionReason.PROVIDER_ERROR,
                        message=f"Deep analysis failed: {e}",
                    )
                )

        # Stage 8: Final diversification
        final_diversified = apply_final_diversification(
            final_candidates,
            self._universe_provider,
            max_per_group=self._settings.discovery_max_per_group,
        )

        # Stage 9: Final ranking and selection
        # Re-rank final candidates by score
        final_diversified.sort(key=lambda c: (-float(c.opportunity_score.total), c.symbol))
        final_selected = []
        for i, candidate in enumerate(final_diversified[:final_k]):
            final_selected.append(
                Candidate(
                    symbol=candidate.symbol,
                    rank=i + 1,
                    direction=candidate.direction,
                    opportunity_score=candidate.opportunity_score,
                    market_state=candidate.market_state,
                    reasons=candidate.reasons,
                    warnings=candidate.warnings,
                    data_quality_status=candidate.data_quality_status,
                )
            )

        # Build rejection list
        all_rejections = list(filter_rejections) + list(deep_rejections)

        runtime_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return CandidateSet(
            generated_at=datetime.now(UTC),
            universe_mode=UniverseMode(self._settings.discovery_universe_mode),
            universe_size=universe_size,
            eligible_count=len(eligible_obs),
            rejected_count=len(all_rejections),
            preliminary_count=preliminary_count,
            deep_analysis_count=len(deep_candidates),
            final_count=len(final_selected),
            candidates=tuple(final_selected),
            rejections=tuple(all_rejections),
            runtime_ms=runtime_ms,
        )

    def _build_final_candidate(
        self,
        prelim: PreliminaryCandidate,
        market_state: MarketState,
        rank: int,
    ) -> Candidate:
        """Build final Candidate from preliminary and deep market state."""
        # Validate market state quality
        warnings = []
        if market_state.data_quality.status != "GOOD":
            warnings.append(f"Data quality: {market_state.data_quality.status}")
        if market_state.data_quality.missing_values > 0:
            warnings.append(f"Missing values: {market_state.data_quality.missing_values}")

        return Candidate(
            symbol=prelim.symbol,
            rank=rank,
            direction=prelim.score.direction,
            opportunity_score=prelim.score,
            market_state=market_state,
            reasons=prelim.score.reasons,
            warnings=tuple(warnings),
            data_quality_status=str(market_state.data_quality.status),
        )


def create_discovery_service(
    gateway: MarketDataGateway,
    settings: Settings | None = None,
) -> OpportunityDiscoveryService:
    """Factory function to create discovery service."""
    return OpportunityDiscoveryService(gateway, settings)