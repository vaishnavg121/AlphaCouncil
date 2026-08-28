"""Domain models for M2 Opportunity Discovery.

These models define the typed contracts for the deterministic candidate
generation pipeline.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UniverseMode(StrEnum):
    """Source mode for the tradable universe."""

    CURATED = "curated"
    ALPACA = "alpaca"


class AssetCategory(StrEnum):
    """Asset classification for diversification."""

    EQUITY = "EQUITY"
    ETF = "ETF"
    UNKNOWN = "UNKNOWN"


class SignalDirection(StrEnum):
    """Directional evidence for opportunity signals."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    MIXED = "MIXED"
    NEUTRAL = "NEUTRAL"


class RejectionReason(StrEnum):
    """Explicit reasons for candidate rejection during filtering."""

    NOT_TRADABLE = "NOT_TRADABLE"
    PRICE_TOO_LOW = "PRICE_TOO_LOW"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    STALE_DATA = "STALE_DATA"
    INVALID_DATA = "INVALID_DATA"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    DATA_QUALITY_DEGRADED = "DATA_QUALITY_DEGRADED"


class CandidateRejection(BaseModel):
    """A symbol that was rejected during the discovery pipeline."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    reason: RejectionReason
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())


class ScreeningObservation(BaseModel):
    """Lightweight market observation from the cheap screening stage.

    Contains only the data needed for preliminary scoring.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime

    # Price
    price: Decimal

    # Returns
    return_1d: Decimal | None = None
    return_5d: Decimal | None = None
    return_20d: Decimal | None = None

    # Volume
    volume: Decimal | None = None
    avg_volume_20: Decimal | None = None
    volume_ratio: Decimal | None = None
    volume_zscore: Decimal | None = None

    # Volatility
    realized_vol_20: Decimal | None = None
    atr_pct: Decimal | None = None

    # Trend / Momentum
    distance_sma20_pct: Decimal | None = None
    distance_sma50_pct: Decimal | None = None
    rsi_14: Decimal | None = None

    # Trend classification
    trend_short: str | None = None
    trend_medium: str | None = None

    # Liquidity
    dollar_volume: Decimal | None = None

    # Data quality
    data_quality_status: str | None = None
    bars_received: int | None = None

    @property
    def has_sufficient_data(self) -> bool:
        """Check if observation has minimum required fields for scoring."""
        required = [
            self.price,
            self.return_5d,
            self.return_20d,
            self.avg_volume_20,
            self.volume,
            self.realized_vol_20,
            self.distance_sma20_pct,
            self.rsi_14,
        ]
        return all(v is not None for v in required)


class OpportunityScore(BaseModel):
    """Deterministic, explainable opportunity score with component breakdown.

    All component scores are normalized to 0-100 range.
    Total is weighted average of components.
    """

    model_config = ConfigDict(frozen=True)

    total: Decimal
    momentum: Decimal
    trend: Decimal
    volume: Decimal
    volatility: Decimal
    mean_reversion: Decimal
    liquidity: Decimal
    quality: Decimal

    # Directional evidence
    direction: SignalDirection

    # Explainability
    reasons: tuple[str, ...] = ()
    reason_contributions: dict[str, Decimal] = {}

    @property
    def is_viable(self) -> bool:
        """Check if score meets minimum threshold for candidate consideration."""
        return float(self.total) >= 30.0


class PreliminaryCandidate(BaseModel):
    """A candidate after preliminary screening but before deep M1 analysis."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    observation: ScreeningObservation
    score: OpportunityScore
    rank: int | None = None


class Candidate(BaseModel):
    """Final candidate for M3 committee consumption.

    Contains full deterministic evidence including M1 MarketState.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    rank: int

    direction: SignalDirection
    opportunity_score: OpportunityScore

    # Full M1 market state (deep analysis)
    market_state: MarketState

    # Evidence from screening
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    # Metadata
    generated_at: datetime = Field(default_factory=lambda: datetime.now())
    data_quality_status: str | None = None


class CandidateSet(BaseModel):
    """Complete output of the discovery pipeline."""

    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    universe_mode: UniverseMode
    universe_size: int
    eligible_count: int
    rejected_count: int
    preliminary_count: int
    deep_analysis_count: int
    final_count: int

    candidates: tuple[Candidate, ...]
    rejections: tuple[CandidateRejection, ...] = ()
    runtime_ms: int = 0


# Forward reference resolution
from app.market.models import MarketState  # noqa: E402

Candidate.model_rebuild()