"""Post-Trade Evaluation and Trading Memory models for M8.

These models define the typed contracts for deterministic post-trade evaluation,
structured trading memory, confidence calibration, and historical analytics.
ZERO LLM calls. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# =============================================================================
# Trade Outcome Classification
# =============================================================================

class TradeOutcomeType(StrEnum):
    """Final trade outcome classification."""

    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    UNKNOWN = "UNKNOWN"


class ThesisCorrectness(StrEnum):
    """Directional thesis evaluation - separate from trade profitability."""

    CORRECT = "CORRECT"
    PARTIALLY_CORRECT = "PARTIALLY_CORRECT"
    INCORRECT = "INCORRECT"
    INCONCLUSIVE = "INCONCLUSIVE"


class CalibrationInsight(StrEnum):
    """Confidence calibration assessment."""

    WELL_CALIBRATED = "WELL_CALIBRATED"
    OVERCONFIDENT = "OVERCONFIDENT"
    UNDERCONFIDENT = "UNDERCONFIDENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AgentStance(StrEnum):
    """Agent stance for historical recording (aligned with M3)."""

    STRONG_LONG = "STRONG_LONG"
    LONG = "LONG"
    NEUTRAL = "NEUTRAL"
    SHORT = "SHORT"
    STRONG_SHORT = "STRONG_SHORT"
    ABSTAIN = "ABSTAIN"


class DisagreementBucket(StrEnum):
    """Normalized disagreement buckets for analytics."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TrendRegime(StrEnum):
    """Trend regime labels from M1 (for regime analytics)."""

    STRONG_UP = "STRONG_UP"
    UP = "UP"
    NEUTRAL = "NEUTRAL"
    DOWN = "DOWN"
    STRONG_DOWN = "STRONG_DOWN"


class ExitReasonCategory(StrEnum):
    """Exit reason categories for analytics."""

    HARD_STOP = "HARD_STOP"
    KILL_SWITCH = "KILL_SWITCH"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    MAX_HOLDING = "MAX_HOLDING"
    THESIS_DETERIORATION = "THESIS_DETERIORATION"
    MAX_LOSS = "MAX_LOSS"
    RISK_REDUCTION = "RISK_REDUCTION"
    RECONCILIATION = "RECONCILIATION"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


# =============================================================================
# Core Trade Record
# =============================================================================

class TradeRecord(BaseModel):
    """Normalized historical trade record with full provenance chain."""

    model_config = ConfigDict(frozen=True)

    # Stable identity
    trade_id: str = Field(default_factory=lambda: str(uuid4()))

    # Provenance chain - NEVER use symbol alone as trade identity
    candidate_id: Optional[str] = None
    committee_result_id: Optional[str] = None
    trade_thesis_id: Optional[str] = None
    risk_evaluation_id: Optional[str] = None
    instrument_plan_id: Optional[str] = None
    entry_execution_id: Optional[str] = None
    position_id: Optional[str] = None
    exit_execution_id: Optional[str] = None

    # Trade basics
    symbol: str
    instrument_type: str  # STOCK, ETF, OPTION
    direction: Literal["LONG", "SHORT"]

    # Timestamps
    discovery_timestamp: Optional[datetime] = None
    thesis_timestamp: Optional[datetime] = None
    entry_timestamp: Optional[datetime] = None
    exit_timestamp: Optional[datetime] = None

    # Prices
    entry_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None

    # Quantities
    entry_quantity: Optional[Decimal] = None
    exit_quantity: Optional[Decimal] = None

    # Notionals
    entry_notional: Optional[Decimal] = None
    exit_notional: Optional[Decimal] = None

    # PnL
    realized_pnl: Optional[Decimal] = None
    return_pct: Optional[Decimal] = None

    # Duration
    holding_duration_seconds: Optional[int] = None

    # MFE / MAE
    mfe_amount: Optional[Decimal] = None
    mfe_pct: Optional[Decimal] = None
    mfe_r_multiple: Optional[Decimal] = None
    mae_amount: Optional[Decimal] = None
    mae_pct: Optional[Decimal] = None
    mae_r_multiple: Optional[Decimal] = None

    # Risk
    initial_risk_amount: Optional[Decimal] = None
    r_multiple: Optional[Decimal] = None
    risk_budget: Optional[Decimal] = None
    max_position_notional: Optional[Decimal] = None
    initial_stop: Optional[Decimal] = None

    # Exit
    exit_reason_codes: tuple[str, ...] = ()

    # Committee
    committee_confidence: Optional[Decimal] = None
    committee_disagreement: Optional[str] = None  # DisagreementBucket value

    # Instrument selection
    instrument_selection_score: Optional[Decimal] = None

    # Risk decision
    risk_decision: Optional[str] = None  # RiskDecisionType value
    constitution_version: Optional[str] = None

    # Data quality
    data_quality_flags: tuple[str, ...] = ()

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    @property
    def is_complete(self) -> bool:
        """Check if trade has minimum required fields for analytics."""
        return (
            self.entry_price is not None
            and self.exit_price is not None
            and self.entry_quantity is not None
            and self.realized_pnl is not None
        )

    def with_update(self, **kwargs: Any) -> TradeRecord:
        """Create updated record with incremented version."""
        data = self.model_dump()
        data.update(kwargs)
        data["version"] = self.version + 1
        data["updated_at"] = datetime.now(UTC)
        return TradeRecord(**data)


class TradeOutcome(BaseModel):
    """Trade outcome with numerical metrics (not just binary win/loss)."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    outcome_type: TradeOutcomeType

    # Numerical metrics
    realized_pnl: Optional[Decimal] = None
    return_pct: Optional[Decimal] = None
    r_multiple: Optional[Decimal] = None
    mfe_pct: Optional[Decimal] = None
    mae_pct: Optional[Decimal] = None
    holding_duration_seconds: Optional[int] = None

    # Computed at evaluation time
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Thesis Evaluation (separate from profitability)
# =============================================================================

class ThesisOutcomeEvaluation(BaseModel):
    """Directional thesis correctness evaluation.

    CRITICAL: This is SEPARATE from trade profitability.
    A trade can be a LOSS while thesis is CORRECT, and vice versa.
    """

    model_config = ConfigDict(frozen=True)

    trade_id: str
    correctness: ThesisCorrectness

    # Underlying movement evidence
    underlying_entry_price: Optional[Decimal] = None
    underlying_exit_price: Optional[Decimal] = None
    underlying_move_pct: Optional[Decimal] = None

    # Materiality threshold used
    materiality_threshold_pct: Decimal = Decimal("0.02")  # 2% default

    # Reasoning
    rationale: str = ""
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_directional_correct(self) -> bool:
        return self.correctness in (ThesisCorrectness.CORRECT, ThesisCorrectness.PARTIALLY_CORRECT)


# =============================================================================
# Execution Quality
# =============================================================================

class ExecutionQualityEvaluation(BaseModel):
    """Execution quality assessment for entry and exit."""

    model_config = ConfigDict(frozen=True)

    trade_id: str

    # Entry
    entry_planned_price: Optional[Decimal] = None
    entry_actual_price: Optional[Decimal] = None
    entry_slippage_amount: Optional[Decimal] = None
    entry_slippage_pct: Optional[Decimal] = None

    # Exit
    exit_planned_price: Optional[Decimal] = None
    exit_actual_price: Optional[Decimal] = None
    exit_slippage_amount: Optional[Decimal] = None
    exit_slippage_pct: Optional[Decimal] = None

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def _calc_slippage_pct(self) -> ExecutionQualityEvaluation:
        # Auto-calculate entry slippage pct if we have the components
        if self.entry_slippage_pct is None and self.entry_slippage_amount is not None and self.entry_planned_price is not None and self.entry_planned_price > 0:
            object.__setattr__(self, 'entry_slippage_pct', self.entry_slippage_amount / self.entry_planned_price)
        if self.exit_slippage_pct is None and self.exit_slippage_amount is not None and self.exit_planned_price is not None and self.exit_planned_price > 0:
            object.__setattr__(self, 'exit_slippage_pct', self.exit_slippage_amount / self.exit_planned_price)
        return self


# =============================================================================
# Exit Quality
# =============================================================================

class ExitQualityEvaluation(BaseModel):
    """Descriptive exit quality metrics (not theoretical optimality)."""

    model_config = ConfigDict(frozen=True)

    trade_id: str

    mfe_pct: Optional[Decimal] = None
    realized_return_pct: Optional[Decimal] = None

    # Captured profit ratio = realized favorable return / MFE
    captured_profit_ratio: Optional[Decimal] = None

    # Giveback from MFE
    giveback_from_mfe_pct: Optional[Decimal] = None

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Risk Outcome
# =============================================================================

class RiskOutcomeEvaluation(BaseModel):
    """Risk outcome evaluation (descriptive, not retrospective mutation)."""

    model_config = ConfigDict(frozen=True)

    trade_id: str

    authorized_risk: Optional[Decimal] = None
    realized_loss: Optional[Decimal] = None
    mae_amount: Optional[Decimal] = None

    # Utilization
    risk_utilization_pct: Optional[Decimal] = None  # realized_loss / authorized_risk

    # Trigger flags
    hard_stop_triggered: bool = False
    kill_switch_triggered: bool = False
    max_loss_triggered: bool = False

    # M4 behavior
    m4_reduced_exposure: bool = False
    reduction_reason: Optional[str] = None

    # Outcome
    loss_within_authorized: Optional[bool] = None

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Instrument Outcome
# =============================================================================

class InstrumentOutcomeEvaluation(BaseModel):
    """Descriptive instrument selection outcome."""

    model_config = ConfigDict(frozen=True)

    trade_id: str

    instrument_type: str  # STOCK, ETF, OPTION
    selection_score: Optional[Decimal] = None

    # Liquidity quality
    avg_spread_pct: Optional[Decimal] = None
    avg_dollar_volume: Optional[Decimal] = None

    # Execution quality
    execution_quality: Optional[ExecutionQualityEvaluation] = None

    # Capital/risk utilization
    capital_utilization_pct: Optional[Decimal] = None
    risk_utilization_pct: Optional[Decimal] = None

    # Result
    trade_outcome: Optional[TradeOutcomeType] = None

    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Agent Performance
# =============================================================================

class AgentPerformanceRecord(BaseModel):
    """Per-agent performance for a specific trade."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    agent_name: str  # QUANT, BULL, BEAR, REGIME

    # Agent's original opinion
    stance: AgentStance
    confidence: Decimal = Field(ge=0, le=1)

    participated: bool = True
    abstained: bool = False

    # Evidence
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()

    # Outcome comparison
    direction_correct: Optional[bool] = None
    calibration_target: Optional[int] = None  # 1=correct, 0=incorrect, None=inconclusive

    # Committee context
    committee_agreement: Optional[bool] = None  # Agreed with final committee direction?

    # Trade result
    trade_profitable: Optional[bool] = None
    r_multiple: Optional[Decimal] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Committee Performance Aggregates
# =============================================================================

class CommitteePerformanceSummary(BaseModel):
    """Aggregate committee performance statistics."""

    model_config = ConfigDict(frozen=True)

    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0

    directional_accuracy: Optional[Decimal] = None
    win_rate: Optional[Decimal] = None

    mean_r_multiple: Optional[Decimal] = None
    median_r_multiple: Optional[Decimal] = None
    mean_return_pct: Optional[Decimal] = None

    mean_mfe_pct: Optional[Decimal] = None
    mean_mae_pct: Optional[Decimal] = None

    avg_holding_period_seconds: Optional[int] = None

    mean_committee_confidence: Optional[Decimal] = None

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Confidence Calibration
# =============================================================================

class CalibrationBucket(BaseModel):
    """Single confidence calibration bucket."""

    model_config = ConfigDict(frozen=True)

    bucket_low: Decimal  # inclusive
    bucket_high: Decimal  # exclusive (except last bucket)

    sample_count: int = 0
    mean_predicted_confidence: Optional[Decimal] = None
    observed_success_rate: Optional[Decimal] = None
    calibration_gap: Optional[Decimal] = None  # mean_confidence - observed_accuracy


class CalibrationSummary(BaseModel):
    """Complete calibration analysis."""

    model_config = ConfigDict(frozen=True)

    buckets: tuple[CalibrationBucket, ...] = ()
    brier_score: Optional[Decimal] = None
    ece: Optional[Decimal] = None  # Expected Calibration Error
    min_sample_size: int = 20

    overall_insight: CalibrationInsight = CalibrationInsight.INSUFFICIENT_DATA
    total_samples: int = 0

    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Similar Trade Retrieval
# =============================================================================

class SimilarityComponent(BaseModel):
    """Single weighted similarity component."""

    model_config = ConfigDict(frozen=True)

    name: str
    weight: Decimal
    score: Decimal  # 0-1
    max_possible: Decimal = Decimal("1.0")

    matching: bool = False
    details: str = ""


class SimilarTradeResult(BaseModel):
    """Historical trade with similarity score and explanation."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    similarity_score: Decimal  # 0-1
    matching_features: tuple[SimilarityComponent, ...] = ()
    differing_features: tuple[SimilarityComponent, ...] = ()

    # Outcome summary for context
    outcome_type: Optional[TradeOutcomeType] = None
    return_pct: Optional[Decimal] = None
    r_multiple: Optional[Decimal] = None
    direction: Optional[str] = None
    instrument_type: Optional[str] = None
    committee_confidence: Optional[Decimal] = None
    disagreement: Optional[str] = None


# =============================================================================
# Historical Context
# =============================================================================

class HistoricalContext(BaseModel):
    """Structured historical context for decision support."""

    model_config = ConfigDict(frozen=True)

    # Similar trades
    similar_trade_count: int = 0
    top_similar_trade_ids: tuple[str, ...] = ()

    # Aggregate statistics
    win_rate: Optional[Decimal] = None
    directional_accuracy: Optional[Decimal] = None
    mean_r_multiple: Optional[Decimal] = None
    median_r_multiple: Optional[Decimal] = None
    mean_return_pct: Optional[Decimal] = None
    mean_mfe_pct: Optional[Decimal] = None
    mean_mae_pct: Optional[Decimal] = None
    avg_holding_period_seconds: Optional[int] = None

    # Committee calibration
    committee_calibration: Optional[CalibrationSummary] = None

    # Agent historical statistics
    agent_stats: dict[str, dict[str, Any]] = {}

    # Warnings
    warnings: tuple[str, ...] = ()

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_sufficient_samples(self) -> bool:
        return self.similar_trade_count >= 20


# =============================================================================
# Disagreement Analytics
# =============================================================================

class DisagreementAnalytics(BaseModel):
    """Outcomes disaggregated by disagreement level."""

    model_config = ConfigDict(frozen=True)

    bucket: DisagreementBucket
    count: int = 0
    win_rate: Optional[Decimal] = None
    directional_accuracy: Optional[Decimal] = None
    mean_r_multiple: Optional[Decimal] = None
    mean_return_pct: Optional[Decimal] = None


# =============================================================================
# Regime/Trend Analytics
# =============================================================================

class RegimeAnalytics(BaseModel):
    """Outcomes disaggregated by trend regime."""

    model_config = ConfigDict(frozen=True)

    regime: TrendRegime
    count: int = 0
    win_rate: Optional[Decimal] = None
    mean_r_multiple: Optional[Decimal] = None
    directional_accuracy: Optional[Decimal] = None


# =============================================================================
# Exit Reason Analytics
# =============================================================================

class ExitReasonAnalytics(BaseModel):
    """Outcomes disaggregated by exit reason."""

    model_config = ConfigDict(frozen=True)

    reason_category: ExitReasonCategory
    count: int = 0
    mean_r_multiple: Optional[Decimal] = None
    mean_return_pct: Optional[Decimal] = None
    mean_mfe_capture: Optional[Decimal] = None
    mean_holding_duration_seconds: Optional[int] = None


# =============================================================================
# Risk Reduction Analytics
# =============================================================================

class RiskReductionAnalytics(BaseModel):
    """Compare M4 APPROVED vs REDUCED outcomes."""

    model_config = ConfigDict(frozen=True)

    approved_count: int = 0
    reduced_count: int = 0

    approved_win_rate: Optional[Decimal] = None
    reduced_win_rate: Optional[Decimal] = None

    approved_mean_r: Optional[Decimal] = None
    reduced_mean_r: Optional[Decimal] = None

    approved_mae: Optional[Decimal] = None
    reduced_mae: Optional[Decimal] = None

    approved_mfe: Optional[Decimal] = None
    reduced_mfe: Optional[Decimal] = None


# =============================================================================
# Signal Attribution
# =============================================================================

class SignalAttribution(BaseModel):
    """Historical association of M2 signals with outcomes."""

    model_config = ConfigDict(frozen=True)

    signal_name: str  # momentum, trend, volume, volatility, mean_reversion, liquidity, quality
    count: int = 0
    mean_score_when_win: Optional[Decimal] = None
    mean_score_when_loss: Optional[Decimal] = None
    win_rate_above_median: Optional[Decimal] = None
    win_rate_below_median: Optional[Decimal] = None


# =============================================================================
# Memory Query Results
# =============================================================================

class PerformanceSummary(BaseModel):
    """Overall performance summary for API."""

    model_config = ConfigDict(frozen=True)

    total_trades: int = 0
    committee: CommitteePerformanceSummary
    calibration: CalibrationSummary
    disagreement: tuple[DisagreementAnalytics, ...] = ()
    regime: tuple[RegimeAnalytics, ...] = ()
    exit_reasons: tuple[ExitReasonAnalytics, ...] = ()
    risk_reduction: Optional[RiskReductionAnalytics] = None
    signal_attribution: tuple[SignalAttribution, ...] = ()
    agent_performance: dict[str, dict[str, Any]] = {}

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# Configuration Constants
# =============================================================================

# Default materiality threshold for thesis evaluation (2%)
DEFAULT_THESIS_MATERIALITY_THRESHOLD_PCT = Decimal("0.02")

# Minimum sample size for calibration conclusions
MIN_CALIBRATION_SAMPLE_SIZE = 20

# Default calibration buckets
DEFAULT_CALIBRATION_BUCKETS = [
    (Decimal("0.50"), Decimal("0.60")),
    (Decimal("0.60"), Decimal("0.70")),
    (Decimal("0.70"), Decimal("0.80")),
    (Decimal("0.80"), Decimal("0.90")),
    (Decimal("0.90"), Decimal("1.00")),
]

# Default similarity weights (must sum to 1.0)
DEFAULT_SIMILARITY_WEIGHTS = {
    "direction_match": Decimal("0.20"),
    "trend_regime_similarity": Decimal("0.15"),
    "volatility_similarity": Decimal("0.15"),
    "momentum_similarity": Decimal("0.10"),
    "rsi_similarity": Decimal("0.10"),
    "confidence_similarity": Decimal("0.10"),
    "disagreement_similarity": Decimal("0.10"),
    "instrument_match": Decimal("0.10"),
}


def get_default_calibration_buckets() -> list[tuple[Decimal, Decimal]]:
    """Get default calibration bucket boundaries."""
    return list(DEFAULT_CALIBRATION_BUCKETS)


def get_default_similarity_weights() -> dict[str, Decimal]:
    """Get default similarity weights."""
    return dict(DEFAULT_SIMILARITY_WEIGHTS)


# Rebuild models to resolve forward references
PerformanceSummary.model_rebuild()