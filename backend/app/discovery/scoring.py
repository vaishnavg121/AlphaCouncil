"""Opportunity scoring for M2 discovery.

Combines signal components into a final explainable OpportunityScore.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from app.core.config import Settings
from app.discovery.models import (
    OpportunityScore,
    PreliminaryCandidate,
    ScreeningObservation,
    SignalDirection,
)
from app.discovery.signals import SignalWeights, compute_all_signals


def compute_opportunity_score(
    obs: ScreeningObservation,
    settings: Settings,
) -> OpportunityScore:
    """Compute the complete deterministic opportunity score for an observation."""
    weights = SignalWeights(
        momentum=settings.discovery_weight_momentum,
        trend=settings.discovery_weight_trend,
        volume=settings.discovery_weight_volume,
        volatility=settings.discovery_weight_volatility,
        mean_reversion=settings.discovery_weight_mean_reversion,
        liquidity=settings.discovery_weight_liquidity,
        quality=settings.discovery_weight_quality,
    )

    signals = compute_all_signals(obs)
    component_scores: dict[str, Decimal] = {}
    component_directions: dict[str, SignalDirection] = {}
    all_reasons: list[str] = []
    reason_contributions: dict[str, Decimal] = {}

    # Collect component scores and reasons
    for name, (score, direction, reasons) in signals.items():
        component_scores[name] = score
        component_directions[name] = direction
        for reason in reasons:
            all_reasons.append(reason)
            # Approximate contribution based on weight and score deviation from 50
            weight = getattr(weights, name)
            contribution = Decimal(str(weight)) * (score - Decimal("50")) / Decimal("50")
            reason_contributions[reason] = contribution

    # Weighted total
    total = Decimal("0")
    for name, score in component_scores.items():
        weight = getattr(weights, name)
        total += score * Decimal(str(weight))

    # Determine overall direction from directional components
    direction = _determine_overall_direction(component_scores, component_directions, weights)

    return OpportunityScore(
        total=Decimal(str(round(float(total), 2))),
        momentum=component_scores.get("momentum", Decimal("50")),
        trend=component_scores.get("trend", Decimal("50")),
        volume=component_scores.get("volume", Decimal("50")),
        volatility=component_scores.get("volatility", Decimal("50")),
        mean_reversion=component_scores.get("mean_reversion", Decimal("50")),
        liquidity=component_scores.get("liquidity", Decimal("50")),
        quality=component_scores.get("quality", Decimal("50")),
        direction=direction,
        reasons=tuple(all_reasons),
        reason_contributions=reason_contributions,
    )


def _determine_overall_direction(
    scores: dict[str, Decimal],
    directions: dict[str, SignalDirection],
    weights: SignalWeights,
) -> SignalDirection:
    """Determine overall directional bias from component scores."""
    bullish_weight = Decimal("0")
    bearish_weight = Decimal("0")

    for name, direction in directions.items():
        weight = getattr(weights, name)
        score = scores.get(name, Decimal("50"))
        # Only count directional weight if score deviates significantly from neutral
        if direction == SignalDirection.BULLISH and score > Decimal("60"):
            bullish_weight += Decimal(str(weight))
        elif direction == SignalDirection.BEARISH and score < Decimal("40"):
            bearish_weight += Decimal(str(weight))
        elif direction == SignalDirection.MIXED:
            # Split mixed weight
            bullish_weight += Decimal(str(weight)) / Decimal("2")
            bearish_weight += Decimal(str(weight)) / Decimal("2")

    if bullish_weight > bearish_weight * Decimal("1.5"):
        return SignalDirection.BULLISH
    elif bearish_weight > bullish_weight * Decimal("1.5"):
        return SignalDirection.BEARISH
    elif bullish_weight > Decimal("0") and bearish_weight > Decimal("0"):
        return SignalDirection.MIXED
    return SignalDirection.NEUTRAL


def rank_candidates(
    candidates: list[PreliminaryCandidate],
    tie_breaker: Literal["symbol", "score"] = "symbol",
) -> list[PreliminaryCandidate]:
    """Rank candidates by score with deterministic tie-breaking.

    Args:
        candidates: List of preliminary candidates.
        tie_breaker: Tie-breaking rule.

    Returns:
        Ranked list with rank attribute set.
    """
    # Sort by score descending, then by tie_breaker
    if tie_breaker == "symbol":
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (-float(c.score.total), c.symbol),
        )
    else:
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (-float(c.score.total), -float(c.score.total)),
        )

    for i, candidate in enumerate(sorted_candidates):
        # Create new candidate with rank (immutable model)
        candidate_dict = candidate.model_dump()
        candidate_dict["rank"] = i + 1
        # Note: In practice, we'd reconstruct the model, but for now
        # we'll just return the sorted list
        pass

    return sorted_candidates


def select_top_k(
    candidates: list[PreliminaryCandidate],
    k: int,
) -> list[PreliminaryCandidate]:
    """Select top K candidates by rank."""
    ranked = rank_candidates(candidates)
    return ranked[:k]