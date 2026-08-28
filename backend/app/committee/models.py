"""Domain models for M3 Adversarial Investment Committee.

These models define the typed contracts for the agent-based committee system.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentRole(StrEnum):
    """Committee agent roles."""

    QUANT = "QUANT"
    BULL = "BULL"
    BEAR = "BEAR"
    REGIME = "REGIME"


class AgentStance(StrEnum):
    """Agent directional stance."""

    STRONG_LONG = "STRONG_LONG"
    LONG = "LONG"
    NEUTRAL = "NEUTRAL"
    SHORT = "SHORT"
    STRONG_SHORT = "STRONG_SHORT"
    ABSTAIN = "ABSTAIN"


class DisagreementSeverity(StrEnum):
    """Severity of disagreement among agents."""

    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CommitteeDecision(StrEnum):
    """Final committee decision."""

    PROPOSE_LONG = "PROPOSE_LONG"
    PROPOSE_SHORT = "PROPOSE_SHORT"
    NO_TRADE = "NO_TRADE"


class NoTradeReason(StrEnum):
    """Explicit reasons for NO_TRADE decision."""

    LOW_CONVICTION = "LOW_CONVICTION"
    HIGH_DISAGREEMENT = "HIGH_DISAGREEMENT"
    INSUFFICIENT_ANALYSIS = "INSUFFICIENT_ANALYSIS"
    POOR_DATA_QUALITY = "POOR_DATA_QUALITY"
    MIXED_EVIDENCE = "MIXED_EVIDENCE"
    NO_DIRECTIONAL_EDGE = "NO_DIRECTIONAL_EDGE"


class EvidenceCategory(StrEnum):
    """Categories of evidence items."""

    PRICE = "PRICE"
    RETURNS = "RETURNS"
    MOMENTUM = "MOMENTUM"
    TREND = "TREND"
    VOLATILITY = "VOLATILITY"
    VOLUME = "VOLUME"
    LIQUIDITY = "LIQUIDITY"
    TECHNICAL = "TECHNICAL"
    DATA_QUALITY = "DATA_QUALITY"
    DISCOVERY = "DISCOVERY"


class EvidenceSource(StrEnum):
    """Source of evidence."""

    M1_FEATURE = "M1_FEATURE"
    M2_DISCOVERY = "M2_DISCOVERY"
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"


class AgentStatus(StrEnum):
    """Agent execution status."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"


# Stance numeric mapping for deterministic aggregation
STANCE_VALUE = {
    AgentStance.STRONG_LONG: 2,
    AgentStance.LONG: 1,
    AgentStance.NEUTRAL: 0,
    AgentStance.SHORT: -1,
    AgentStance.STRONG_SHORT: -2,
    AgentStance.ABSTAIN: None,  # ABSTAIN is distinct from NEUTRAL
}


class EvidenceItem(BaseModel):
    """A single piece of structured evidence with stable ID."""

    model_config = ConfigDict(frozen=True)

    id: str
    category: EvidenceCategory
    label: str
    value: str
    unit: str | None = None
    timestamp: datetime | None = None
    source: EvidenceSource = EvidenceSource.M1_FEATURE
    quality: str | None = None


class EvidencePacket(BaseModel):
    """Structured evidence packet supplied to all committee agents.

    Immutable evidence that all agents share.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    as_of: datetime
    candidate_rank: int | None = None
    opportunity_score: Decimal | None = None
    discovery_direction: str | None = None

    # Core evidence items with stable IDs
    evidence: tuple[EvidenceItem, ...] = ()

    # Data quality
    data_quality_status: str | None = None
    data_quality_warnings: tuple[str, ...] = ()

    # Discovery context
    discovery_reasons: tuple[str, ...] = ()

    def get_evidence(self, evidence_id: str) -> EvidenceItem | None:
        """Retrieve evidence item by ID."""
        for item in self.evidence:
            if item.id == evidence_id:
                return item
        return None

    def get_evidence_by_category(self, category: EvidenceCategory) -> tuple[EvidenceItem, ...]:
        """Get all evidence items of a specific category."""
        return tuple(item for item in self.evidence if item.category == category)


class AgentOpinion(BaseModel):
    """Structured opinion from a committee agent."""

    model_config = ConfigDict(frozen=True)

    agent_role: AgentRole
    symbol: str
    stance: AgentStance
    confidence: Decimal = Field(ge=0, le=1)

    # Thesis
    thesis: str

    # Evidence grounding
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()

    # Risk assessment
    key_risks: tuple[str, ...] = ()

    # Invalidation conditions
    invalidation_conditions: tuple[str, ...] = ()

    # Uncertainty acknowledgment
    uncertainties: tuple[str, ...] = ()

    # Abstention
    abstain_reason: str | None = None

    # Round tracking
    round: int = 1

    # Metadata
    prompt_version: str = "v1"
    model: str | None = None
    latency_ms: int = 0

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: Decimal) -> Decimal:
        if v < 0 or v > 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v

    @field_validator("stance")
    @classmethod
    def _validate_abstain_consistency(cls, v: AgentStance, info: object) -> AgentStance:
        if v == AgentStance.ABSTAIN:
            # If abstaining, confidence should be low or zero
            pass
        return v

    @property
    def stance_value(self) -> int | None:
        """Numeric value for deterministic aggregation."""
        return STANCE_VALUE.get(self.stance)

    @property
    def is_directional(self) -> bool:
        """Whether the stance expresses a directional view."""
        return self.stance in (
            AgentStance.STRONG_LONG,
            AgentStance.LONG,
            AgentStance.SHORT,
            AgentStance.STRONG_SHORT,
        )

    @property
    def is_bullish(self) -> bool:
        return self.stance in (AgentStance.STRONG_LONG, AgentStance.LONG)

    @property
    def is_bearish(self) -> bool:
        return self.stance in (AgentStance.STRONG_SHORT, AgentStance.SHORT)


class AgentChallenge(BaseModel):
    """Targeted challenge from one agent to another."""

    model_config = ConfigDict(frozen=True)

    target_agent: AgentRole
    source_agents: tuple[AgentRole, ...]
    symbol: str

    # Opposing views being challenged
    opposing_stances: dict[AgentRole, AgentStance] = {}

    # Specific evidence being challenged
    challenged_evidence_ids: tuple[str, ...] = ()

    # Concise challenge summary
    challenge_summary: str

    # Round when challenge was issued
    round: int = 2


class AgentResult(BaseModel):
    """Result of agent execution with status."""

    model_config = ConfigDict(frozen=True)

    agent_role: AgentRole
    status: AgentStatus
    opinion: AgentOpinion | None = None
    error: str | None = None
    latency_ms: int = 0
    attempts: int = 1


class DisagreementReport(BaseModel):
    """Deterministic disagreement analysis."""

    model_config = ConfigDict(frozen=True)

    severity: DisagreementSeverity
    stance_spread: int  # max - min stance values (excluding ABSTAIN)
    conflicting_agents: tuple[AgentRole, ...] = ()
    conflicting_evidence_ids: tuple[str, ...] = ()
    challenge_required: bool = False

    # Detailed breakdown
    bullish_agents: tuple[AgentRole, ...] = ()
    bearish_agents: tuple[AgentRole, ...] = ()
    neutral_agents: tuple[AgentRole, ...] = ()
    abstaining_agents: tuple[AgentRole, ...] = ()


class CommitteeDecisionModel(BaseModel):
    """Final committee decision with deterministic scoring."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    decision: CommitteeDecision
    direction: SignalDirection | None = None

    # Scoring
    committee_score: Decimal = Field(ge=0, le=100)
    committee_confidence: Decimal = Field(ge=0, le=1)

    # Disagreement
    initial_disagreement: DisagreementSeverity
    final_disagreement: DisagreementSeverity

    # Participation
    participating_agents: tuple[AgentRole, ...] = ()
    abstained_agents: tuple[AgentRole, ...] = ()
    failed_agents: tuple[AgentRole, ...] = ()

    # Evidence
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()

    # Reasoning
    decision_reasons: tuple[str, ...] = ()
    unresolved_risks: tuple[str, ...] = ()

    # NO_TRADE reason if applicable
    no_trade_reason: NoTradeReason | None = None


class TradeThesis(BaseModel):
    """Structured trade thesis for M4 consumption.

    This is NOT an order - it's an evidence-backed thesis for risk engine.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    proposed_direction: SignalDirection

    committee_confidence: Decimal = Field(ge=0, le=1)

    # Summary
    summary: str

    # Evidence
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()

    # Risk
    key_risks: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()

    # Metadata
    market_state_as_of: datetime
    candidate_score: Decimal
    committee_decision: CommitteeDecisionModel

    # No position sizing, order instructions, or execution details


class CommitteeResult(BaseModel):
    """Complete auditable committee result."""

    model_config = ConfigDict(frozen=True)

    candidate_symbol: str
    evidence_packet: EvidencePacket

    # Initial opinions
    initial_opinions: tuple[AgentOpinion, ...] = ()

    # Disagreement
    disagreement_report: DisagreementReport | None = None

    # Rebuttal
    challenges: tuple[AgentChallenge, ...] = ()
    final_opinions: tuple[AgentOpinion, ...] = ()

    # Final decision
    decision: CommitteeDecisionModel

    # Trade thesis if applicable
    trade_thesis: TradeThesis | None = None

    # Metadata
    generated_at: datetime = Field(default_factory=lambda: datetime.now())
    total_runtime_ms: int = 0
    total_llm_calls: int = 0
    model: str | None = None


# Forward reference resolution for SignalDirection
from app.market.models import SignalDirection  # noqa: E402

# Re-export SignalDirection for external use
__all__ = ["SignalDirection"]

# Rebuild models that reference SignalDirection
AgentOpinion.model_rebuild()
CommitteeDecisionModel.model_rebuild()
TradeThesis.model_rebuild()