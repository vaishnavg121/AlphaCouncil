"""Council orchestration service for M9 end-to-end pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, cast

from app.alpaca.gateway import AlpacaGateway
from app.committee.models import (
    AgentOpinion,
    AgentRole,
    AgentStance,
    CommitteeDecision,
    CommitteeDecisionModel,
    CommitteeResult,
    DisagreementReport,
    DisagreementSeverity,
    EvidenceCategory,
    EvidenceItem,
    EvidencePacket,
    EvidenceSource,
    TradeThesis,
)
from app.committee.service import InvestmentCommitteeService as CommitteeService
from app.committee.service import create_committee_service
from app.core.config import Settings
from app.discovery.service import OpportunityDiscoveryService, create_discovery_service
from app.execution.models import (
    ExecutionPlan,
    ExecutionReasonCode,
    ExecutionStatus,
    OrderSide,
    OrderType,
    TimeInForce,
)
from app.execution.models import InstrumentType as ExecutionInstrumentType
from app.execution.service import ExecutionService, create_execution_service
from app.execution.store import ExecutionStore
from app.instruments.models import (
    EquityInstrumentPlan,
    EquitySide,
    InstrumentPlan,
    InstrumentType,
)
from app.instruments.selector import InstrumentSelectorService
from app.market.gateway import MarketDataGateway
from app.market.models import SignalDirection
from app.memory.service import TradingMemoryService, create_trading_memory_service
from app.orchestration.models import (
    CandidateAnalysis,
    CouncilRun,
    CouncilRunEvent,
    CouncilRunEventType,
    CouncilRunRequest,
    CouncilRunResponse,
    CouncilRunStatus,
    create_council_run,
)
from app.positions.store import PositionStore
from app.risk.models import (
    RiskBudget,
    RiskCheckResult,
    RiskDecisionType,
    RiskEvaluation,
    RiskReasonCode,
    RiskRuleType,
)
from app.risk.service import RiskEvaluationService, create_risk_evaluation_service


class CouncilOrchestrator:
    """Orchestrates the full AlphaCouncil pipeline."""

    def __init__(
        self,
        settings: Settings | None = None,
        market_gateway: MarketDataGateway | None = None,
        alpaca_gateway: AlpacaGateway | None = None,
        position_store: PositionStore | None = None,
        execution_store: ExecutionStore | None = None,
        memory_service: TradingMemoryService | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.market_gateway = market_gateway
        self.alpaca_gateway = alpaca_gateway
        self.position_store = position_store
        self.execution_store = execution_store
        self.memory_service = memory_service or create_trading_memory_service()

        # Initialize services
        self.discovery_service: OpportunityDiscoveryService | None = None
        self.committee_service: CommitteeService | None = None
        self.risk_service: RiskEvaluationService | None = None
        self.instrument_selector: InstrumentSelectorService | None = None
        self.execution_service: ExecutionService | None = None

        self._current_run: CouncilRun | None = None
        self._event_callbacks: list[Callable[[CouncilRunEvent], None]] = []

    def _init_services(self) -> None:
        """Lazy initialization of services."""
        if self.discovery_service is None:
            assert self.market_gateway is not None, "market_gateway required for discovery"
            self.discovery_service = create_discovery_service(
                self.market_gateway,
                self.settings,
            )

        if self.committee_service is None:
            assert self.market_gateway is not None, "market_gateway required for committee"
            self.committee_service = create_committee_service(
                self.market_gateway,
                self.settings,
            )

        if self.risk_service is None:
            self.risk_service = create_risk_evaluation_service(
                self.market_gateway,
                self.alpaca_gateway,
            )

        if self.instrument_selector is None:
            self.instrument_selector = InstrumentSelectorService(
                settings=self.settings,
            )

        if self.execution_service is None:
            self.execution_service = create_execution_service(
                settings=self.settings,
                market_gateway=self.market_gateway,
                alpaca_gateway=self.alpaca_gateway,
                execution_store=self.execution_store,
            )

    def add_event_callback(self, callback: Callable[[CouncilRunEvent], None]) -> None:
        """Add callback for streaming events."""
        self._event_callbacks.append(callback)

    def _emit_event(
        self,
        run: CouncilRun,
        event_type: CouncilRunEventType,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Emit event to callbacks."""
        event = CouncilRunEvent(
            event_type=event_type,
            run_id=run.run_id,
            message=message,
            data=data or {},
        )
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception:
                pass  # Don't let callback errors break the pipeline

    async def run_council(self, request: CouncilRunRequest) -> CouncilRunResponse:
        """Run the full council pipeline."""
        run = create_council_run(request)
        self._current_run = run
        start_time = time.time()

        try:
            # Emit run started
            self._emit_event(run, CouncilRunEventType.RUN_STARTED, "Council run started")

            # Stage 1: Discovery
            run.status = CouncilRunStatus.DISCOVERING
            self._emit_event(run, CouncilRunEventType.MARKET_SCAN_STARTED, "Market scan started")
            await self._run_discovery_stage(run)

            # Stage 2: Committee
            run.status = CouncilRunStatus.COMMITTEE
            self._emit_event(
                run,
                CouncilRunEventType.COMMITTEE_STARTED,
                "Committee deliberation started",
            )
            await self._run_committee_stage(run)

            # Stage 3: Risk
            run.status = CouncilRunStatus.RISK
            self._emit_event(
                run,
                CouncilRunEventType.RISK_EVALUATION_STARTED,
                "Risk evaluation started",
            )
            await self._run_risk_stage(run)

            # Stage 4: Instrument Selection
            run.status = CouncilRunStatus.INSTRUMENT
            self._emit_event(
                run,
                CouncilRunEventType.INSTRUMENT_SELECTION_STARTED,
                "Instrument selection started",
            )
            await self._run_instrument_stage(run)

            # Stage 5: Execution Planning (dry run)
            run.status = CouncilRunStatus.EXECUTION_PLANNING
            self._emit_event(
                run,
                CouncilRunEventType.EXECUTION_DRY_RUN_STARTED,
                "Execution dry-run started",
            )
            await self._run_execution_stage(run)

            # Complete
            run.status = CouncilRunStatus.COMPLETE
            run.completed_at = datetime.now(UTC)
            self._emit_event(run, CouncilRunEventType.RUN_COMPLETED, "Council run completed")

        except Exception as e:
            run.status = CouncilRunStatus.FAILED
            run.errors.append(str(e))
            self._emit_event(
                run,
                CouncilRunEventType.RUN_FAILED,
                f"Council run failed: {e}",
                {"error": str(e)},
            )
            raise

        finally:
            run.total_runtime_ms = int((time.time() - start_time) * 1000)

        return CouncilRunResponse(
            run_id=run.run_id,
            status=run.status,
            message=f"Run {run.status.value.lower()}",
        )

    async def _run_discovery_stage(self, run: CouncilRun) -> None:
        """Run M2 discovery stage."""
        stage_start = time.time()

        # For demo mode, use synthetic candidates
        if run.demo_mode:
            run.candidate_set = self._create_demo_candidate_set(run)
            run.candidates_discovered = len(run.candidate_set.get("candidates", []))
        else:
            # Real discovery
            self._init_services()
            assert self.discovery_service is not None
            candidate_set = self.discovery_service.discover()
            run.candidate_set = candidate_set.model_dump()
            run.candidates_discovered = candidate_set.final_count

        run.candidates_analyzed = min(run.candidates_discovered, run.max_candidates)
        run.stage_timings["discovery"] = int((time.time() - stage_start) * 1000)

        # Emit candidate events
        candidates_list = run.candidate_set.get("candidates", []) if run.candidate_set else []
        for candidate in candidates_list[:run.max_candidates]:
            self._emit_event(
                run,
                CouncilRunEventType.CANDIDATE_FOUND,
                f"Candidate: {candidate.get('symbol', 'N/A')}",
                {
                    "candidate_id": candidate.get("candidate_id"),
                    "symbol": candidate.get("symbol"),
                    "score": candidate.get("opportunity_score", {}).get("total"),
                },
            )

    async def _run_committee_stage(self, run: CouncilRun) -> None:
        """Run M3 committee stage."""
        candidates = (run.candidate_set.get("candidates", []) if run.candidate_set else [])[:run.max_candidates]

        for i, candidate in enumerate(candidates):
            symbol = candidate.get("symbol", f"UNKNOWN_{i}")

            analysis = CandidateAnalysis(
                candidate_id=candidate["candidate_id"],
                symbol=symbol,
                candidate_rank=i + 1,
                opportunity_score=Decimal(
                    str(candidate.get("opportunity_score", {}).get("total", 0))
                ),
                direction=candidate.get("direction", "NEUTRAL"),
                opportunity=candidate,
            )

            if run.demo_mode:
                result = self._create_demo_committee_result(analysis, i)
                analysis.committee_result_id = f"{analysis.candidate_id}:committee"
                analysis.committee_result = result
                analysis.committee_decision = result.decision.decision.value
                analysis.committee_confidence = result.decision.committee_confidence
                analysis.committee_disagreement = result.decision.final_disagreement.value
                analysis.agent_opinions = {
                    opinion.agent_role.value: opinion.model_dump(mode="json")
                    for opinion in result.final_opinions
                }
            else:
                # Real committee - would call committee service
                pass

            run.candidate_analyses.append(analysis)
            self._emit_event(
                run,
                CouncilRunEventType.AGENT_COMPLETED,
                f"Committee analyzed {symbol}",
                {
                    "candidate_id": analysis.candidate_id,
                    "symbol": symbol,
                    "decision": analysis.committee_decision,
                },
            )

        self._emit_event(
            run,
            CouncilRunEventType.COMMITTEE_COMPLETED,
            "Committee deliberation completed",
        )

    async def _run_risk_stage(self, run: CouncilRun) -> None:
        """Run M4 risk evaluation stage."""
        for analysis in run.candidate_analyses:
            if run.demo_mode:
                evaluation = self._create_demo_risk_evaluation(analysis)
                analysis.risk_evaluation_id = f"{analysis.candidate_id}:risk"
                analysis.risk_evaluation = evaluation
                analysis.risk_decision = evaluation.decision.value
                analysis.risk_reason = evaluation.reason_code.value
                if evaluation.risk_budget is not None:
                    analysis.risk_budget = evaluation.risk_budget.adjusted_risk_budget
                    analysis.max_position_notional = evaluation.risk_budget.max_position_notional
            else:
                # Real risk evaluation
                pass

            if analysis.risk_decision in {"APPROVED", "REDUCED"}:
                run.candidates_approved += 1
            else:
                run.candidates_rejected += 1

            self._emit_event(
                run,
                CouncilRunEventType.RISK_DECISION,
                f"Risk decision for {analysis.symbol}: {analysis.risk_decision}",
                {
                    "candidate_id": analysis.candidate_id,
                    "symbol": analysis.symbol,
                    "decision": analysis.risk_decision,
                },
            )

    async def _run_instrument_stage(self, run: CouncilRun) -> None:
        """Run M5 instrument selection stage."""
        for analysis in run.candidate_analyses:
            if analysis.risk_decision == "REJECTED":
                analysis.instrument_type = "NO_TRADE"
                analysis.instrument_selection_reason = "M4 risk rejected the candidate"
                analysis.stop_reason_codes = ("M4_RISK_REJECTED",)
                analysis.status = "STOPPED"
                continue

            if run.demo_mode:
                plan = self._create_demo_instrument_plan(analysis)
                analysis.instrument_plan = plan
                analysis.instrument_type = plan.instrument_type.value
                analysis.instrument_selection_reason = (
                    plan.no_trade_reason
                    if plan.is_no_trade
                    else "Equity plan created within the M4 risk ceiling"
                )
                if plan.is_no_trade:
                    analysis.stop_reason_codes = ("INSTRUMENT_NO_TRADE",)
                    analysis.status = "STOPPED"
            else:
                # Real instrument selection
                pass

            self._emit_event(
                run,
                CouncilRunEventType.INSTRUMENT_SELECTED,
                f"Instrument selected for {analysis.symbol}: {analysis.instrument_type}",
                {
                    "candidate_id": analysis.candidate_id,
                    "symbol": analysis.symbol,
                    "type": analysis.instrument_type,
                },
            )

    async def _run_execution_stage(self, run: CouncilRun) -> None:
        """Run M6 execution planning (dry run) stage."""
        for analysis in run.candidate_analyses:
            if analysis.risk_decision == "REJECTED":
                analysis.execution_reason_codes = (ExecutionReasonCode.RISK_REJECTED,)
                analysis.execution_status = ExecutionStatus.NOT_EXECUTED
                continue

            if analysis.instrument_type == "NO_TRADE":
                analysis.execution_reason_codes = (ExecutionReasonCode.UPSTREAM_NO_TRADE,)
                analysis.execution_status = ExecutionStatus.NOT_EXECUTED
                continue

            if run.demo_mode:
                plan = self._create_demo_execution_plan(analysis)
                analysis.execution_plan_id = plan.execution_plan_id
                analysis.execution_plan = plan
                analysis.execution_authorized = False
                analysis.execution_status = ExecutionStatus.NOT_EXECUTED
                analysis.execution_reason_codes = (ExecutionReasonCode.EXECUTION_DISABLED,)
                analysis.dry_run = True
                analysis.status = "COMPLETE"
            else:
                # Real execution planning
                pass

            self._emit_event(
                run,
                CouncilRunEventType.EXECUTION_AUTHORIZED,
                f"Execution plan created for {analysis.symbol} (not submitted)",
                {
                    "candidate_id": analysis.candidate_id,
                    "symbol": analysis.symbol,
                    "dry_run": analysis.dry_run,
                    "submitted": False,
                },
            )

    def _create_demo_candidate_set(self, run: CouncilRun) -> dict[str, Any]:
        """Create synthetic candidate set for demo mode."""
        specs = [
            ("SPY", "BULLISH", "82.5", "84", "79", "61", "22", "95", "512.30"),
            ("QQQ", "BULLISH", "78.3", "80", "76", "58", "25", "92", "486.10"),
            ("AAPL", "BEARISH", "75.1", "68", "63", "44", "28", "90", "229.40"),
            ("TSLA", "BULLISH", "71.2", "72", "69", "56", "48", "58", "318.20"),
            ("NVDA", "BULLISH", "69.8", "74", "71", "64", "52", "88", "124.80"),
        ]
        candidates = []
        for rank, (
            symbol,
            direction,
            total,
            trend,
            momentum,
            rsi,
            volatility,
            liquidity,
            price,
        ) in enumerate(specs, 1):
            candidate_id = f"{run.run_id}:candidate:{rank}:{symbol}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "symbol": symbol,
                    "rank": rank,
                    "direction": direction,
                    "trend": trend,
                    "momentum": momentum,
                    "rsi": rsi,
                    "volatility": volatility,
                    "liquidity": liquidity,
                    "reference_price": price,
                    "status": "SELECTED",
                    "synthetic_demo": True,
                    "opportunity_score": {
                        "total": total,
                        "direction": direction,
                        "trend": trend,
                        "momentum": momentum,
                        "volatility": volatility,
                        "liquidity": liquidity,
                    },
                    "reasons": ["SYNTHETIC_DEMO", "DETERMINISTIC_CANDIDATE_ORDER"],
                }
            )
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "universe_mode": "curated",
            "universe_size": 64,
            "eligible_count": 12,
            "rejected_count": 52,
            "preliminary_count": 15,
            "deep_analysis_count": 8,
            "final_count": 5,
            "candidates": candidates,
            "rejections": [],
            "runtime_ms": 150,
            "synthetic_demo": True,
        }

    def _create_demo_committee_result(
        self,
        analysis: CandidateAnalysis,
        index: int,
    ) -> CommitteeResult:
        """Create structured, candidate-specific M3 output without any LLM call."""
        now = datetime.now(UTC)
        bullish = analysis.direction == "BULLISH"
        direction = SignalDirection.BULLISH if bullish else SignalDirection.BEARISH
        decision = CommitteeDecision.PROPOSE_LONG if bullish else CommitteeDecision.PROPOSE_SHORT
        confidence = (
            Decimal("0.78"),
            Decimal("0.74"),
            Decimal("0.45"),
            Decimal("0.68"),
            Decimal("0.76"),
        )[index]
        disagreement = (
            DisagreementSeverity.LOW
            if index in {0, 4}
            else DisagreementSeverity.MEDIUM
        )
        momentum_id = f"{analysis.candidate_id}:momentum"
        trend_id = f"{analysis.candidate_id}:trend"
        evidence = (
            EvidenceItem(
                id=momentum_id,
                category=EvidenceCategory.MOMENTUM,
                label="Momentum score",
                value=str(analysis.opportunity.get("momentum", "")),
                source=EvidenceSource.M2_DISCOVERY,
            ),
            EvidenceItem(
                id=trend_id,
                category=EvidenceCategory.TREND,
                label="Trend score",
                value=str(analysis.opportunity.get("trend", "")),
                source=EvidenceSource.M2_DISCOVERY,
            ),
        )
        packet = EvidencePacket(
            symbol=analysis.symbol,
            as_of=now,
            candidate_rank=analysis.candidate_rank,
            opportunity_score=analysis.opportunity_score,
            discovery_direction=analysis.direction,
            evidence=evidence,
            data_quality_status="SYNTHETIC_DEMO",
            discovery_reasons=("SYNTHETIC_DEMO", "DETERMINISTIC_CANDIDATE_ORDER"),
        )
        directional_stance = AgentStance.LONG if bullish else AgentStance.SHORT
        counter_role = AgentRole.BEAR if bullish else AgentRole.BULL
        opinions = tuple(
            AgentOpinion(
                agent_role=role,
                symbol=analysis.symbol,
                stance=(
                    AgentStance.NEUTRAL
                    if role == counter_role
                    else directional_stance
                ),
                confidence={
                    AgentRole.QUANT: Decimal("0.80"),
                    AgentRole.BULL: Decimal("0.85") if bullish else Decimal("0.40"),
                    AgentRole.BEAR: Decimal("0.40") if bullish else Decimal("0.82"),
                    AgentRole.REGIME: Decimal("0.70"),
                }[role],
                thesis=(
                    "Structured momentum and trend evidence support the proposed direction."
                    if role != counter_role
                    else "Counter-case remains material, so the agent stays neutral."
                ),
                supporting_evidence_ids=(momentum_id, trend_id) if role != counter_role else (),
                contradicting_evidence_ids=(momentum_id,) if role == counter_role else (),
                key_risks=("Synthetic demo evidence only; no live market inference.",),
                invalidation_conditions=("Direction no longer agrees with the trend signal.",),
                uncertainties=("External providers are not required for Demo Mode.",),
                model="synthetic-demo",
            )
            for role in AgentRole
        )
        participating = tuple(opinion.agent_role for opinion in opinions)
        decision_model = CommitteeDecisionModel(
            symbol=analysis.symbol,
            decision=decision,
            direction=direction,
            committee_score=analysis.opportunity_score or Decimal("0"),
            committee_confidence=confidence,
            initial_disagreement=disagreement,
            final_disagreement=disagreement,
            participating_agents=participating,
            supporting_evidence_ids=(momentum_id, trend_id),
            decision_reasons=("M2_SIGNAL_ALIGNMENT", "STRUCTURED_AGENT_MAJORITY"),
            unresolved_risks=("SYNTHETIC_DEMO_INPUT",),
        )
        thesis = TradeThesis(
            symbol=analysis.symbol,
            proposed_direction=direction,
            committee_confidence=confidence,
            summary=f"Synthetic demo proposal for {analysis.symbol} from canonical M2 evidence.",
            supporting_evidence_ids=(momentum_id, trend_id),
            key_risks=("SYNTHETIC_DEMO_INPUT",),
            invalidation_conditions=("M2 direction invalidated",),
            market_state_as_of=now,
            candidate_score=analysis.opportunity_score or Decimal("0"),
            committee_decision=decision_model,
        )
        return CommitteeResult(
            candidate_symbol=analysis.symbol,
            evidence_packet=packet,
            initial_opinions=opinions,
            disagreement_report=DisagreementReport(
                severity=disagreement,
                stance_spread=1,
                conflicting_agents=(counter_role,),
                challenge_required=False,
                bullish_agents=tuple(
                    opinion.agent_role for opinion in opinions if opinion.is_bullish
                ),
                bearish_agents=tuple(
                    opinion.agent_role for opinion in opinions if opinion.is_bearish
                ),
                neutral_agents=tuple(
                    opinion.agent_role
                    for opinion in opinions
                    if opinion.stance == AgentStance.NEUTRAL
                ),
            ),
            final_opinions=opinions,
            decision=decision_model,
            trade_thesis=thesis,
            generated_at=now,
            total_llm_calls=0,
            model="synthetic-demo",
        )

    def _create_demo_risk_evaluation(
        self,
        analysis: CandidateAnalysis,
    ) -> RiskEvaluation:
        """Create an actual deterministic M4 result for the demo provenance chain."""
        confidence_passed = analysis.symbol != "AAPL"
        hard_checks = [
            RiskCheckResult(rule_name="Kill Switch", rule_type=RiskRuleType.HARD_GATE, passed=True),
            RiskCheckResult(
                rule_name="Daily Loss Limit",
                rule_type=RiskRuleType.HARD_GATE,
                passed=True,
            ),
            RiskCheckResult(
                rule_name="Max Drawdown",
                rule_type=RiskRuleType.HARD_GATE,
                passed=True,
            ),
            RiskCheckResult(
                rule_name="Committee Confidence",
                rule_type=RiskRuleType.HARD_GATE,
                passed=confidence_passed,
                reason_code=(
                    None if confidence_passed else RiskReasonCode.LOW_COMMITTEE_CONFIDENCE
                ),
                detail=(
                    "Confidence meets the deterministic threshold."
                    if confidence_passed
                    else "Committee confidence is below the deterministic threshold."
                ),
            ),
        ]
        if not confidence_passed:
            return RiskEvaluation(
                symbol=analysis.symbol,
                decision=RiskDecisionType.REJECTED,
                reason_code=RiskReasonCode.LOW_COMMITTEE_CONFIDENCE,
                checks=tuple(hard_checks),
                constitution_version="v1.0.0",
            )

        volatility_reduced = analysis.symbol == "NVDA"
        soft_checks = [
            RiskCheckResult(
                rule_name="Volatility Reduction",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=not volatility_reduced,
                reason_code=(
                    RiskReasonCode.VOLATILITY_REDUCTION if volatility_reduced else None
                ),
                detail=(
                    "Volatility adjustment reduces the risk budget by 25%."
                    if volatility_reduced
                    else "No volatility reduction required."
                ),
                reduction_factor=Decimal("0.75") if volatility_reduced else Decimal("1"),
            ),
            RiskCheckResult(
                rule_name="Liquidity Reduction",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=True,
                reduction_factor=Decimal("1"),
            ),
            RiskCheckResult(
                rule_name="Symbol Concentration",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=True,
                reduction_factor=Decimal("1"),
            ),
        ]
        adjusted = Decimal("750") if volatility_reduced else Decimal("1000")
        maximum = Decimal("7500") if volatility_reduced else Decimal("5000")
        return RiskEvaluation(
            symbol=analysis.symbol,
            decision=(
                RiskDecisionType.REDUCED
                if volatility_reduced
                else RiskDecisionType.APPROVED
            ),
            reason_code=(
                RiskReasonCode.VOLATILITY_REDUCTION
                if volatility_reduced
                else RiskReasonCode.WITHIN_LIMITS
            ),
            checks=tuple(hard_checks + soft_checks),
            risk_budget=RiskBudget(
                base_risk_budget=Decimal("1000"),
                volatility_reduction=Decimal("0.75") if volatility_reduced else Decimal("1"),
                adjusted_risk_budget=adjusted,
                atr_stop_distance=Decimal("10"),
                max_position_notional=maximum,
                shares=75 if volatility_reduced else 50,
                limiting_rule=(
                    RiskReasonCode.VOLATILITY_REDUCTION if volatility_reduced else None
                ),
            ),
            constitution_version="v1.0.0",
        )

    def _create_demo_instrument_plan(self, analysis: CandidateAnalysis) -> InstrumentPlan:
        """Create a typed M5 plan or an explicit typed no-trade outcome."""
        if analysis.symbol == "TSLA":
            return InstrumentPlan(
                plan_id=f"{analysis.candidate_id}:instrument",
                symbol=analysis.symbol,
                thesis_direction=cast(Literal["BULLISH", "BEARISH"], analysis.direction or "BULLISH"),
                instrument_type=InstrumentType.NO_TRADE,
                underlying_symbol=analysis.symbol,
                risk_evaluation_id=analysis.risk_evaluation_id,
                no_trade_reason="NO_VIABLE_INSTRUMENT",
                selection_reasons=("INSTRUMENT_NO_TRADE", "SYNTHETIC_LIQUIDITY_GUARD"),
            )

        evaluation = analysis.risk_evaluation
        budget = evaluation.risk_budget if evaluation is not None else None
        if budget is None:
            raise ValueError("M4_RISK_BUDGET_MISSING")
        reference_price = Decimal(str(analysis.opportunity["reference_price"]))
        side = EquitySide.LONG if analysis.direction == "BULLISH" else EquitySide.SHORT
        quantity = budget.max_position_notional / reference_price
        equity_plan = EquityInstrumentPlan(
            symbol=analysis.symbol,
            side=side,
            reference_price=reference_price,
            max_notional=budget.max_position_notional,
            planned_notional=budget.max_position_notional,
            estimated_quantity=quantity,
            fractional_supported=True,
            risk_budget_used=budget.adjusted_risk_budget,
            estimated_loss_at_risk_stop=budget.adjusted_risk_budget,
            selection_score=analysis.opportunity_score or Decimal("0"),
            selection_reasons=("M4_BUDGET_AVAILABLE", "EQUITY_LIQUIDITY_ACCEPTABLE"),
            warnings=("SYNTHETIC_DEMO_PLAN",),
        )
        return InstrumentPlan(
            plan_id=f"{analysis.candidate_id}:instrument",
            symbol=analysis.symbol,
            thesis_direction=cast(Literal["BULLISH", "BEARISH"], analysis.direction or "BULLISH"),
            instrument_type=InstrumentType.STOCK,
            underlying_symbol=analysis.symbol,
            risk_evaluation_id=analysis.risk_evaluation_id,
            constitution_version="v1.0.0",
            equity_plan=equity_plan,
            selection_reasons=equity_plan.selection_reasons,
            warnings=equity_plan.warnings,
        )

    def _create_demo_execution_plan(self, analysis: CandidateAnalysis) -> ExecutionPlan:
        """Create a typed M6 plan without authorizing or submitting any order."""
        instrument_plan = analysis.instrument_plan
        if instrument_plan is None or instrument_plan.equity_plan is None:
            raise ValueError("INSTRUMENT_PLAN_MISSING")
        equity = instrument_plan.equity_plan
        now = datetime.now(UTC)
        bid = equity.reference_price - Decimal("0.05")
        ask = equity.reference_price + Decimal("0.05")
        side = OrderSide.BUY if equity.side == EquitySide.LONG else OrderSide.SELL
        return ExecutionPlan(
            execution_plan_id=f"{analysis.candidate_id}:execution",
            instrument_plan_id=instrument_plan.plan_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.execution_plan_ttl_seconds),
            symbol=analysis.symbol,
            instrument_type=ExecutionInstrumentType.STOCK,
            direction=cast(Literal["BULLISH", "BEARISH"], analysis.direction or "BULLISH"),
            side=side,
            quantity=equity.estimated_quantity,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=equity.reference_price,
            fresh_bid=bid,
            fresh_ask=ask,
            fresh_mid=equity.reference_price,
            fresh_quote_timestamp=now,
            limit_price=ask if side == OrderSide.BUY else bid,
            expected_notional=equity.planned_notional,
            risk_budget=equity.risk_budget_used,
            max_authorized_notional=equity.max_notional,
            constitution_version=instrument_plan.constitution_version,
            warnings=("SYNTHETIC_DEMO", "PLAN_ONLY", "NOT_SUBMITTED"),
            reason_codes=(ExecutionReasonCode.WITHIN_LIMITS,),
        )

    def get_current_run(self) -> CouncilRun | None:
        """Get the current run."""
        return self._current_run


def create_council_orchestrator(
    settings: Settings | None = None,
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
    position_store: PositionStore | None = None,
    execution_store: ExecutionStore | None = None,
    memory_service: TradingMemoryService | None = None,
) -> CouncilOrchestrator:
    """Factory function to create council orchestrator."""
    return CouncilOrchestrator(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
        execution_store=execution_store,
        memory_service=memory_service,
    )
