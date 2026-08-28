"""Diversification and redundancy control for M2 discovery.

Prevents sector/category concentration in final candidate set.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from app.discovery.models import Candidate, PreliminaryCandidate, SignalDirection
from app.discovery.universe import UniverseProvider


def apply_diversification(
    candidates: list[PreliminaryCandidate],
    universe_provider: UniverseProvider,
    max_per_group: int = 3,
    group_by: Literal["category", "sector"] = "category",
) -> list[PreliminaryCandidate]:
    """Apply diversification caps to candidate list.

    Args:
        candidates: Ranked preliminary candidates.
        universe_provider: Provider for asset categorization.
        max_per_group: Maximum candidates per group.
        group_by: Grouping dimension.

    Returns:
        Diversified candidate list preserving rank order where possible.
    """
    if group_by == "category":
        return _diversify_by_category(candidates, universe_provider, max_per_group)
    # Sector diversification would require external metadata
    return candidates


def _diversify_by_category(
    candidates: list[PreliminaryCandidate],
    universe_provider: UniverseProvider,
    max_per_group: int,
) -> list[PreliminaryCandidate]:
    """Limit candidates per asset category (EQUITY/ETF)."""
    category_counts: dict[str, int] = defaultdict(int)
    diversified = []

    for candidate in candidates:
        category = universe_provider.get_asset_category(candidate.symbol)
        if category_counts[category] < max_per_group:
            diversified.append(candidate)
            category_counts[category] += 1

    return diversified


def apply_directional_balance(
    candidates: list[PreliminaryCandidate],
    min_bullish: int = 0,
    min_bearish: int = 0,
) -> list[PreliminaryCandidate]:
    """Ensure minimum directional representation (optional, off by default).

    This is a soft constraint - only applies if minimums are set > 0.
    """
    if min_bullish <= 0 and min_bearish <= 0:
        return candidates

    bullish = [c for c in candidates if c.score.direction == SignalDirection.BULLISH]
    bearish = [c for c in candidates if c.score.direction == SignalDirection.BEARISH]
    mixed = [c for c in candidates if c.score.direction in (SignalDirection.MIXED, SignalDirection.NEUTRAL)]

    result = []

    # Add minimum required from each direction
    for c in bullish[:min_bullish]:
        result.append(c)
    for c in bearish[:min_bearish]:
        result.append(c)

    # Fill remaining slots preserving original rank order
    remaining_slots = len(candidates) - len(result)
    for c in candidates:
        if c not in result and remaining_slots > 0:
            result.append(c)
            remaining_slots -= 1

    return result[:len(candidates)]


def apply_final_diversification(
    candidates: list[Candidate],
    universe_provider: UniverseProvider,
    max_per_group: int = 3,
    group_by: Literal["category", "sector"] = "category",
) -> list[Candidate]:
    """Apply diversification to final Candidate objects (with MarketState)."""
    if group_by == "category":
        return _diversify_final_by_category(candidates, universe_provider, max_per_group)
    return candidates


def _diversify_final_by_category(
    candidates: list[Candidate],
    universe_provider: UniverseProvider,
    max_per_group: int,
) -> list[Candidate]:
    category_counts: dict[str, int] = defaultdict(int)
    diversified = []

    for candidate in candidates:
        category = universe_provider.get_asset_category(candidate.symbol)
        if category_counts[category] < max_per_group:
            diversified.append(candidate)
            category_counts[category] += 1

    return diversified