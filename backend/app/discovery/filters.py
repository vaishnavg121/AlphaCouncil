"""Hard filters for M2 discovery pipeline.

Deterministic eligibility filters applied before scoring.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from app.core.config import Settings
from app.discovery.models import (
    CandidateRejection,
    RejectionReason,
    ScreeningObservation,
)


class FilterConfig:
    """Centralized filter thresholds from settings."""

    def __init__(self, settings: Settings) -> None:
        self.min_price = Decimal(str(settings.discovery_min_price))
        self.min_avg_dollar_volume = Decimal(str(settings.discovery_min_avg_dollar_volume))
        self.min_history_bars = settings.discovery_min_history_bars

    def validate(self) -> None:
        """Validate filter thresholds."""
        if self.min_price < 0:
            raise ValueError("min_price must be non-negative")
        if self.min_avg_dollar_volume < 0:
            raise ValueError("min_avg_dollar_volume must be non-negative")
        if self.min_history_bars < 1:
            raise ValueError("min_history_bars must be positive")


def apply_hard_filters(
    observations: list[ScreeningObservation],
    settings: Settings,
) -> tuple[list[ScreeningObservation], list[CandidateRejection]]:
    """Apply hard eligibility filters to screening observations.

    Returns:
        Tuple of (eligible_observations, rejections)
    """
    config = FilterConfig(settings)
    config.validate()

    eligible = []
    rejections = []

    for obs in observations:
        rejection = _check_observation(obs, config)
        if rejection is None:
            eligible.append(obs)
        else:
            rejections.append(rejection)

    return eligible, rejections


def _check_observation(
    obs: ScreeningObservation,
    config: FilterConfig,
) -> CandidateRejection | None:
    """Check a single observation against all hard filters."""

    # 1. Price floor
    if obs.price is not None and obs.price < config.min_price:
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.PRICE_TOO_LOW,
            message=f"Price {obs.price} below minimum {config.min_price}",
        )

    # 2. Liquidity floor (dollar volume)
    if obs.dollar_volume is not None and obs.dollar_volume < config.min_avg_dollar_volume:
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.LOW_LIQUIDITY,
            message=f"Avg dollar volume {obs.dollar_volume} below minimum {config.min_avg_dollar_volume}",
        )

    # 3. Insufficient history
    if obs.bars_received is not None and obs.bars_received < config.min_history_bars:
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.INSUFFICIENT_HISTORY,
            message=f"Only {obs.bars_received} bars, need at least {config.min_history_bars}",
        )

    # 4. Stale data (no recent bar)
    # Note: This would need a timestamp check; for now we check if price exists
    if obs.price is None:
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.STALE_DATA,
            message="No current price available",
        )

    # 5. Invalid data (NaN/Infinity checks are in indicators, but verify key fields)
    if not obs.has_sufficient_data:
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.INVALID_DATA,
            message="Insufficient valid fields for scoring",
        )

    # 6. Data quality degraded
    if obs.data_quality_status in ("DEGRADED", "INSUFFICIENT", "STALE"):
        return CandidateRejection(
            symbol=obs.symbol,
            reason=RejectionReason.DATA_QUALITY_DEGRADED,
            message=f"Data quality: {obs.data_quality_status}",
        )

    return None


def filter_by_universe_mode(
    symbols: list[str],
    mode: Literal["curated", "alpaca"],
    settings: Settings,
) -> list[str]:
    """Filter symbols based on universe mode (placeholder for future expansion)."""
    if mode == "curated":
        # Curated mode uses predefined list; symbols already filtered
        return symbols
    # For alpaca mode, additional filtering could be applied here
    return symbols