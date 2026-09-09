"""Committee service orchestrating the M3 adversarial investment committee."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.committee.agents.bear import BearAgent
from app.committee.agents.bull import BullAgent
from app.committee.agents.quant import QuantAgent
from app.committee.agents.regime import RegimeAgent
from app.committee.aggregation import CommitteeAggregator
from app.committee.disagreement import detect_disagreement, generate_challenges, run_rebuttal_round
from app.committee.evidence import build_evidence_packet
from app.committee.models import (
    AgentOpinion,
    AgentResult,
    AgentStatus,
    CommitteeDecision,
    CommitteeDecisionModel,
    CommitteeResult,
    EvidencePacket,
    TradeThesis,
)
from app.core.config import Settings
from app.discovery.models import Candidate
from app.market.gateway import MarketDataGateway
from app.market.models import SignalDirection


class InvestmentCommitteeService:
    """Orchestrates the complete M3 adversarial committee pipeline."""

    def __init__(
        self,
        gateway: MarketDataGateway,
        settings: Settings | None = None,
        max_candidates: int = 1,
        agent_concurrency: int = 1,
        enable_rebuttal: bool = True,
    ) -> None:
        self._settings = settings or Settings()
        self._max_candidates = max_candidates
        self._agent_concurrency = agent_concurrency
        self._enable_rebuttal = enable_rebuttal

        # Initialize agents
        self._agents = {
            "QUANT": QuantAgent(self._settings),
            "BULL": BullAgent(self._settings),
            "BEAR": BearAgent(self._settings),
            "REGIME": RegimeAgent(self._settings),
        }
        self._agent_list = [
            self._agents["QUANT"],
            self._agents["BULL"],
            self._agents["BEAR"],
            self._agents["REGIME"],
        ]

        # Aggregator
        self._aggregator = CommitteeAggregator()

    def evaluate_candidate(self, candidate: Candidate) -> CommitteeResult:
        """Evaluate a single candidate through the full committee pipeline."""
        start_time = datetime.now(UTC)
        total_llm_calls = 0

        # Step 1: Build evidence packet
        evidence = build_evidence_packet(candidate)

        # Step 2: Run independent Round 1
        initial_results = self._run_independent_round(evidence)
        total_llm_calls += sum(r.attempts for r in initial_results)

        initial_opinions = self._successful_opinions(initial_results)

        # Step 3: Detect disagreement
        disagreement = detect_disagreement(initial_opinions)

        # Step 4: Rebuttal round if needed
        final_opinions: list[AgentOpinion]
        if self._enable_rebuttal and disagreement.challenge_required:
            challenges = generate_challenges(initial_opinions, disagreement)

            # Map agent role to agent instance
            agents_map = {agent.role.value: agent for agent in self._agent_list}
            rebuttal_opinions = run_rebuttal_round(
                agents=agents_map,
                evidence=evidence,
                challenges=challenges,
                initial_opinions=initial_opinions,
            )

            # Merge rebuttal results - use rebuttal if available, else initial
            final_opinions = []
            for init_op in initial_opinions:
                rebuttal = next((r for r in rebuttal_opinions if r.agent_role == init_op.agent_role), None)
                if rebuttal and rebuttal.round == 2:
                    final_opinions.append(rebuttal)
                else:
                    final_opinions.append(init_op)
            total_llm_calls += sum(r.attempts for r in initial_results)
            # Rebuttal opinions are AgentOpinion objects, not AgentResult
            # We can't track their attempts directly, but we can estimate
        else:
            final_opinions = initial_opinions

        # Step 5: Final disagreement detection
        final_disagreement = detect_disagreement(final_opinions)

        # Step 6: Aggregate
        agent_results = [
            AgentResult(
                agent_role=o.agent_role,
                status=AgentStatus.SUCCESS,
                opinion=o,
            ) for o in final_opinions
        ]

        # Add failed agents from initial results
        for init in initial_results:
            if init.status != AgentStatus.SUCCESS or not init.opinion:
                agent_results.append(init)

        aggregation_result = self._aggregator.aggregate(
            agent_results,
            initial_disagreement=disagreement,
            final_disagreement=final_disagreement,
        )

        # Build decision model
        decision = CommitteeDecisionModel(
            symbol=candidate.symbol,
            decision=aggregation_result["decision"],
            direction=aggregation_result.get("direction"),
            committee_score=aggregation_result["committee_score"],
            committee_confidence=aggregation_result["committee_confidence"],
            initial_disagreement=disagreement.severity,
            final_disagreement=aggregation_result["final_disagreement"],
            participating_agents=aggregation_result["participating_agents"],
            abstained_agents=aggregation_result["abstained_agents"],
            failed_agents=aggregation_result["failed_agents"],
            supporting_evidence_ids=aggregation_result["supporting_evidence_ids"],
            contradicting_evidence_ids=aggregation_result["contradicting_evidence_ids"],
            decision_reasons=aggregation_result["decision_reasons"],
            unresolved_risks=aggregation_result["unresolved_risks"],
            no_trade_reason=aggregation_result["no_trade_reason"],
        )

        # Build TradeThesis if applicable
        trade_thesis = None
        if decision.decision in (
            CommitteeDecision.PROPOSE_LONG,
            CommitteeDecision.PROPOSE_SHORT,
        ):
            trade_thesis = TradeThesis(
                symbol=candidate.symbol,
                proposed_direction=SignalDirection(decision.direction) if decision.direction else SignalDirection.BULLISH,
                committee_confidence=decision.committee_confidence,
                summary=self._synthesize_thesis(decision, final_opinions),
                supporting_evidence_ids=decision.supporting_evidence_ids,
                contradicting_evidence_ids=decision.contradicting_evidence_ids,
                key_risks=decision.unresolved_risks,
                invalidation_conditions=self._collect_invalidation_conditions(final_opinions),
                market_state_as_of=datetime.now(UTC),
                candidate_score=candidate.opportunity_score.total,
                committee_decision=decision,
            )

        runtime_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        return CommitteeResult(
            candidate_symbol=candidate.symbol,
            evidence_packet=build_evidence_packet(candidate),
            initial_opinions=tuple(initial_opinions),
            disagreement_report=disagreement,
            challenges=tuple([]),  # TODO: track challenges
            final_opinions=tuple(final_opinions),
            decision=decision,
            trade_thesis=trade_thesis,
            generated_at=datetime.now(UTC),
            total_runtime_ms=runtime_ms,
            total_llm_calls=total_llm_calls,
            model=self._settings.llm_model,
        )

    @staticmethod
    def _successful_opinions(results: Sequence[AgentResult]) -> list[AgentOpinion]:
        return [
            result.opinion
            for result in results
            if result.status == AgentStatus.SUCCESS and result.opinion is not None
        ]

    def _run_independent_round(self, evidence: EvidencePacket) -> list[AgentResult]:
        """Run independent Round 1 analysis for all agents sequentially."""
        results: list[AgentResult] = []
        for agent in self._agent_list:
            result = agent.analyze(evidence)
            results.append(result)
        return results

    def _synthesize_thesis(
        self,
        decision: CommitteeDecisionModel,
        opinions: Sequence[AgentOpinion],
    ) -> str:
        """Synthesize concise thesis from decision and opinions."""
        supporting = [o for o in opinions if o.is_bullish]
        opposing = [o for o in opinions if o.is_bearish]

        parts = []
        if supporting:
            parts.append(f"Bullish case supported by: {', '.join(o.agent_role.value for o in supporting)}")
        if opposing:
            parts.append(f"Bearish concerns from: {', '.join(o.agent_role.value for o in opposing)}")

        return "; ".join(parts) if parts else "Committee consensus"

    def _collect_invalidation_conditions(
        self,
        opinions: Sequence[AgentOpinion],
    ) -> tuple[str, ...]:
        """Collect all invalidation conditions from opinions."""
        conditions: set[str] = set()
        for o in opinions:
            conditions.update(o.invalidation_conditions)
        return tuple(conditions)

    def evaluate_candidate_set(
        self,
        candidates: Sequence[Candidate],
    ) -> list[CommitteeResult]:
        """Evaluate multiple candidates (respecting max_candidates limit)."""
        results: list[CommitteeResult] = []
        for candidate in candidates[:self._max_candidates]:
            results.append(self.evaluate_candidate(candidate))
        return results


def create_committee_service(
    gateway: MarketDataGateway,
    settings: Settings | None = None,
    max_candidates: int = 1,
    agent_concurrency: int = 1,
    enable_rebuttal: bool = True,
) -> InvestmentCommitteeService:
    """Factory function to create committee service."""
    return InvestmentCommitteeService(
        gateway,
        settings,
        max_candidates=max_candidates,
        agent_concurrency=agent_concurrency,
        enable_rebuttal=enable_rebuttal,
    )
