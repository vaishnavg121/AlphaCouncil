"""Deterministic committee aggregation for M3."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Protocol, TypedDict

from app.committee.models import (
    AgentResult,
    AgentRole,
    AgentStance,
    CommitteeDecision,
    DisagreementSeverity,
    NoTradeReason,
)
from app.market.models import SignalDirection


class DisagreementLike(Protocol):
    """Protocol for objects with severity attribute."""
    severity: DisagreementSeverity


class AggregationResult(TypedDict):
    """Typed boundary between deterministic aggregation and the service layer."""

    decision: CommitteeDecision
    direction: SignalDirection | None
    committee_score: Decimal
    committee_confidence: Decimal
    participating_agents: tuple[AgentRole, ...]
    abstained_agents: tuple[AgentRole, ...]
    failed_agents: tuple[AgentRole, ...]
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]
    decision_reasons: tuple[str, ...]
    unresolved_risks: tuple[str, ...]
    no_trade_reason: NoTradeReason | None
    final_disagreement: DisagreementSeverity


# Agent weights (normalized internally)
DEFAULT_WEIGHTS = {
    "QUANT": 0.30,
    "BULL": 0.25,
    "BEAR": 0.25,
    "REGIME": 0.20,
}

# Minimum successful agents required
MIN_SUCCESSFUL_AGENTS = 3

# Minimum total weight of successful agents
MIN_SUCCESSFUL_WEIGHT = 0.6

# Disagreement penalty factors
DISAGREEMENT_PENALTIES = {
    "NONE": Decimal("1.0"),
    "LOW": Decimal("0.95"),
    "MEDIUM": Decimal("0.85"),
    "HIGH": Decimal("0.70"),
}


def aggregate_opinions(
    opinions: list[AgentResult],
    weights: dict[str, float] | None = None,
    disagreement: DisagreementLike | None = None,
) -> AggregationResult:
    """Aggregate agent opinions into committee decision deterministically.

    Returns:
        Dict with committee_score, committee_confidence, decision, etc.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    # Normalize weights
    total_weight = sum(weights.values())
    norm_weights = {k: Decimal(str(v / total_weight)) for k, v in weights.items()}

    # Filter successful non-abstaining opinions
    valid_opinions: list[AgentResult] = [
        o for o in opinions
        if hasattr(o, 'status') and o.status == "SUCCESS" and o.opinion is not None
        and o.opinion.stance != "ABSTAIN"
    ]

    if len(valid_opinions) < MIN_SUCCESSFUL_AGENTS:
        return {
            "decision": CommitteeDecision.NO_TRADE,
            "direction": None,
            "committee_score": Decimal("0"),
            "committee_confidence": Decimal("0"),
            "participating_agents": (),
            "abstained_agents": (),
            "failed_agents": tuple(
                result.agent_role for result in opinions if result.status != "SUCCESS"
            ),
            "supporting_evidence_ids": tuple(),
            "contradicting_evidence_ids": tuple(),
            "decision_reasons": tuple(),
            "unresolved_risks": tuple(),
            "no_trade_reason": NoTradeReason.INSUFFICIENT_ANALYSIS,
            "final_disagreement": DisagreementSeverity.NONE,
        }

    # Check weight coverage
    successful_weight = sum(
        (norm_weights.get(o.agent_role.value, Decimal("0")) for o in valid_opinions),
        Decimal("0")
    )
    if successful_weight < Decimal(str(MIN_SUCCESSFUL_WEIGHT)):
        return {
            "decision": CommitteeDecision.NO_TRADE,
            "direction": None,
            "committee_score": Decimal("0"),
            "committee_confidence": Decimal("0"),
            "participating_agents": (),
            "abstained_agents": (),
            "failed_agents": tuple(
                result.agent_role for result in opinions if result.status != "SUCCESS"
            ),
            "supporting_evidence_ids": tuple(),
            "contradicting_evidence_ids": tuple(),
            "decision_reasons": tuple(),
            "unresolved_risks": tuple(),
            "no_trade_reason": NoTradeReason.INSUFFICIENT_ANALYSIS,
            "final_disagreement": DisagreementSeverity.NONE,
        }

    # Calculate weighted stance
    weighted_stance = Decimal("0")
    total_confidence_weight = Decimal("0")

    for result in valid_opinions:
        opinion = result.opinion
        assert opinion is not None
        weight = norm_weights.get(opinion.agent_role.value, Decimal("0"))
        stance_val = Decimal(str(opinion.stance_value or 0))
        confidence = opinion.confidence

        weighted_stance += stance_val * weight * confidence
        total_confidence_weight += weight * confidence

    # Normalize weighted stance to -1 to 1 range
    if total_confidence_weight > 0:
        normalized_stance = weighted_stance / total_confidence_weight
    else:
        normalized_stance = Decimal("0")

    # Apply disagreement penalty
    disagreement_penalty = Decimal("1.0")
    if disagreement and hasattr(disagreement, 'severity'):
        penalty = DISAGREEMENT_PENALTIES.get(disagreement.severity, Decimal("1.0"))
        disagreement_penalty = penalty

    # Calculate committee score (0-100)
    # Map stance -1 to 1 to 0-100, then apply penalty
    base_score = (normalized_stance + 1) * 50 * disagreement_penalty
    committee_score = max(Decimal("0"), min(Decimal("100"), base_score))

    # Committee confidence
    confidence_values = (
        result.opinion.confidence
        for result in valid_opinions
        if result.opinion is not None
    )
    avg_confidence = sum(confidence_values, Decimal("0")) / Decimal(
        str(len(valid_opinions))
    )
    committee_confidence = avg_confidence * disagreement_penalty

    # Determine decision
    if committee_score >= 60:
        decision = CommitteeDecision.PROPOSE_LONG
        direction = SignalDirection.BULLISH
    elif committee_score <= 40:
        decision = CommitteeDecision.PROPOSE_SHORT
        direction = SignalDirection.BEARISH
    else:
        decision = CommitteeDecision.NO_TRADE
        direction = None

    # Determine NO_TRADE reason if applicable
    no_trade_reason = None
    if decision == CommitteeDecision.NO_TRADE:
        if len(valid_opinions) < MIN_SUCCESSFUL_AGENTS:
            no_trade_reason = NoTradeReason.INSUFFICIENT_ANALYSIS
        elif disagreement and disagreement.severity in ("HIGH", "MEDIUM"):
            no_trade_reason = NoTradeReason.HIGH_DISAGREEMENT
        elif committee_confidence < Decimal("0.5"):
            no_trade_reason = NoTradeReason.LOW_CONVICTION
        else:
            no_trade_reason = NoTradeReason.MIXED_EVIDENCE

    # Collect evidence IDs
    supporting_ids: set[str] = set()
    contradicting_ids: set[str] = set()
    for r in valid_opinions:
        assert r.opinion is not None
        supporting_ids.update(r.opinion.supporting_evidence_ids)
        contradicting_ids.update(r.opinion.contradicting_evidence_ids)

    # Decision reasons
    reasons = []
    for r in valid_opinions:
        assert r.opinion is not None
        if r.opinion.stance != "ABSTAIN":
            reasons.append(
                f"{r.agent_role.value}: {r.opinion.thesis[:100]}"
            )

    # Unresolved risks
    risks: set[str] = set()
    for r in valid_opinions:
        assert r.opinion is not None
        risks.update(r.opinion.key_risks)

    # Participating agents
    participating = tuple(result.agent_role for result in valid_opinions)
    abstained = tuple(
        result.agent_role
        for result in opinions
        if result.opinion is not None and result.opinion.stance == "ABSTAIN"
    )
    failed = tuple(
        result.agent_role for result in opinions if result.status != "SUCCESS"
    )

    return {
        "decision": decision,
        "direction": direction,
        "committee_score": committee_score,
        "committee_confidence": committee_confidence,
        "participating_agents": participating,
        "abstained_agents": abstained,
        "failed_agents": failed,
        "supporting_evidence_ids": tuple(supporting_ids),
        "contradicting_evidence_ids": tuple(contradicting_ids),
        "decision_reasons": tuple(reasons),
        "unresolved_risks": tuple(risks),
        "no_trade_reason": no_trade_reason,
        "final_disagreement": DisagreementSeverity.NONE,
    }


def _compute_disagreement_penalty(opinions: list[AgentResult]) -> Decimal:
    """Compute penalty factor based on disagreement among opinions."""
    valid = [o for o in opinions if o.status == "SUCCESS" and o.opinion is not None and o.opinion.stance != "ABSTAIN"]
    if len(valid) < 2:
        return Decimal("1.0")

    stances = [o.opinion.stance for o in valid if o.opinion is not None]
    stance_counts = Counter(stances)

    # High disagreement if multiple strong opposing views
    if AgentStance.STRONG_LONG in stances and AgentStance.STRONG_SHORT in stances:
        return Decimal("0.70")
    if AgentStance.LONG in stances and AgentStance.SHORT in stances:
        return Decimal("0.85")
    if len(stance_counts) >= 3:
        return Decimal("0.90")

    return Decimal("1.0")


class CommitteeAggregator:
    """Deterministic committee aggregator."""

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        min_agents: int = MIN_SUCCESSFUL_AGENTS,
        min_weight: float = MIN_SUCCESSFUL_WEIGHT,
    ):
        self.weights = weights or DEFAULT_WEIGHTS
        self.min_agents = min_agents
        self.min_weight = min_weight

    def aggregate(
        self,
        agent_results: list[AgentResult],
        initial_disagreement: DisagreementLike | None = None,
        final_disagreement: DisagreementLike | None = None,
    ) -> AggregationResult:
        """Aggregate agent results into final committee decision."""
        # Build result
        result = aggregate_opinions(
            [r for r in agent_results if r.status == "SUCCESS" and r.opinion is not None],
            weights=self.weights,
            disagreement=final_disagreement,
        )

        # Add disagreement info
        result["final_disagreement"] = final_disagreement.severity if final_disagreement else DisagreementSeverity.NONE

        return result


def determine_final_decision(aggregation_result: AggregationResult) -> AggregationResult:
    """Final decision determination with all edge cases."""
    result = aggregation_result.copy()

    # Override decision if critical issues
    if result.get("decision") == "NO_TRADE":
        pass  # Keep NO_TRADE

    # Ensure confidence bounds
    conf = result["committee_confidence"]
    if conf > 1:
        result["committee_confidence"] = Decimal("1")
    elif conf < 0:
        result["committee_confidence"] = Decimal("0")

    return result
