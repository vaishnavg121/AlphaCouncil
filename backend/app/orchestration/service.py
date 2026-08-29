"""Council orchestration service for M9 end-to-end pipeline."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import uuid4

from app.orchestration.models import (
    CouncilRun,
    CouncilRunRequest,
    CouncilRunResponse,
    CouncilRunStatus,
    CouncilRunEvent,
    CouncilRunEventType,
    CandidateAnalysis,
    create_council_run,
)
from app.discovery.service import OpportunityDiscoveryService, create_discovery_service
from app.committee.service import InvestmentCommitteeService as CommitteeService, create_committee_service
from app.risk.service import RiskEvaluationService, create_risk_evaluation_service
from app.instruments.selector import InstrumentSelectorService
from app.execution.service import ExecutionService, create_execution_service
from app.memory.service import TradingMemoryService, create_trading_memory_service
from app.market.alpaca_gateway import AlpacaMarketDataGateway
from app.alpaca.gateway import AlpacaGateway
from app.positions.store import PositionStore


class CouncilOrchestrator:
    """Orchestrates the full AlphaCouncil pipeline."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        market_gateway: Optional["AlpacaMarketDataGateway"] = None,
        alpaca_gateway: Optional["AlpacaGateway"] = None,
        position_store: Optional["PositionStore"] = None,
        memory_service: Optional[TradingMemoryService] = None,
    ) -> None:
        self.settings = settings or Settings()
        self.market_gateway = market_gateway
        self.alpaca_gateway = alpaca_gateway
        self.position_store = position_store
        self.memory_service = memory_service or create_trading_memory_service()

        # Initialize services
        self.discovery_service: Optional[OpportunityDiscoveryService] = None
        self.committee_service: Optional[CommitteeService] = None
        self.risk_service: Optional[RiskEvaluationService] = None
        self.instrument_selector: Optional[InstrumentSelectorService] = None
        self.execution_service: Optional[ExecutionService] = None

        self._current_run: Optional[CouncilRun] = None
        self._event_callbacks: list = []

    def _init_services(self) -> None:
        """Lazy initialization of services."""
        if self.discovery_service is None:
            self.discovery_service = create_discovery_service(
                settings=self.settings,
                market_gateway=self.market_gateway,
            )

        if self.committee_service is None:
            self.committee_service = create_committee_service(
                settings=self.settings,
            )

        if self.risk_service is None:
            self.risk_service = create_risk_evaluation_service(
                settings=self.settings,
                market_gateway=self.market_gateway,
                alpaca_gateway=self.alpaca_gateway,
            )

        if self.instrument_selector is None:
            self.instrument_selector = InstrumentSelectorService(
                settings=self.settings,
                market_gateway=self.market_gateway,
                alpaca_gateway=self.alpaca_gateway,
            )

        if self.execution_service is None:
            self.execution_service = create_execution_service(
                settings=self.settings,
                market_gateway=self.market_gateway,
                alpaca_gateway=self.alpaca_gateway,
                position_store=self.position_store,
            )

    def add_event_callback(self, callback) -> None:
        """Add callback for streaming events."""
        self._event_callbacks.append(callback)

    def _emit_event(
        self,
        run: CouncilRun,
        event_type: CouncilRunEventType,
        message: str,
        data: dict = None,
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
            self._emit_event(run, CouncilRunEventType.COMMITTEE_STARTED, "Committee deliberation started")
            await self._run_committee_stage(run)

            # Stage 3: Risk
            run.status = CouncilRunStatus.RISK
            self._emit_event(run, CouncilRunEventType.RISK_EVALUATION_STARTED, "Risk evaluation started")
            await self._run_risk_stage(run)

            # Stage 4: Instrument Selection
            run.status = CouncilRunStatus.INSTRUMENT
            self._emit_event(run, CouncilRunEventType.INSTRUMENT_SELECTION_STARTED, "Instrument selection started")
            await self._run_instrument_stage(run)

            # Stage 5: Execution Planning (dry run)
            run.status = CouncilRunStatus.EXECUTION_PLANNING
            self._emit_event(run, CouncilRunEventType.EXECUTION_DRY_RUN_STARTED, "Execution dry-run started")
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

        self._init_services()

        # For demo mode, use synthetic candidates
        if run.demo_mode:
            run.candidate_set = self._create_demo_candidate_set()
            run.candidates_discovered = len(run.candidate_set.get("candidates", []))
        else:
            # Real discovery
            candidate_set = await self.discovery_service.discover()
            run.candidate_set = candidate_set.model_dump()
            run.candidates_discovered = candidate_set.final_count

        run.candidates_analyzed = min(run.candidates_discovered, run.max_candidates)
        run.stage_timings["discovery"] = int((time.time() - time.time()) * 1000)

        # Emit candidate events
        for candidate in run.candidate_set.get("candidates", [])[:run.max_candidates]:
            self._emit_event(
                self._current_run,
                CouncilRunEventType.CANDIDATE_FOUND,
                f"Candidate: {candidate.get('symbol', 'N/A')}",
                {"symbol": candidate.get("symbol"), "score": candidate.get("opportunity_score", {}).get("total")},
            )

    async def _run_committee_stage(self, run: CouncilRun) -> None:
        """Run M3 committee stage."""
        candidates = run.candidate_set.get("candidates", [])[:run.max_candidates]

        for i, candidate in enumerate(candidates):
            symbol = candidate.get("symbol", f"UNKNOWN_{i}")

            analysis = CandidateAnalysis(
                symbol=symbol,
                candidate_rank=i + 1,
                opportunity_score=Decimal(str(candidate.get("opportunity_score", {}).get("total", 0))),
                direction=candidate.get("direction", "NEUTRAL"),
            )

            if run.demo_mode:
                # Demo committee result
                analysis.committee_decision = "PROPOSE_LONG" if i % 2 == 0 else "PROPOSE_SHORT"
                analysis.committee_confidence = Decimal("0.75")
                analysis.committee_disagreement = "LOW"
                analysis.agent_opinions = {
                    "QUANT": {"stance": "LONG", "confidence": "0.80"},
                    "BULL": {"stance": "LONG", "confidence": "0.85"},
                    "BEAR": {"stance": "NEUTRAL", "confidence": "0.40"},
                    "REGIME": {"stance": "LONG", "confidence": "0.70"},
                }
            else:
                # Real committee - would call committee service
                pass

            run.candidate_analyses.append(analysis)
            self._emit_event(
                self._current_run,
                CouncilRunEventType.AGENT_COMPLETED,
                f"Committee analyzed {symbol}",
                {"symbol": symbol, "decision": analysis.committee_decision},
            )

        self._emit_event(self._current_run, CouncilRunEventType.COMMITTEE_COMPLETED, "Committee deliberation completed")

    async def _run_risk_stage(self, run: CouncilRun) -> None:
        """Run M4 risk evaluation stage."""
        for analysis in run.candidate_analyses:
            if run.demo_mode:
                # Demo risk result
                if analysis.committee_decision == "NO_TRADE":
                    analysis.risk_decision = "REJECTED"
                    analysis.risk_reason = "M3_NO_TRADE"
                elif "HIGH" in (analysis.committee_disagreement or ""):
                    analysis.risk_decision = "REJECTED"
                    analysis.risk_reason = "HIGH_DISAGREEMENT"
                else:
                    analysis.risk_decision = "APPROVED"
                    analysis.risk_reason = "WITHIN_LIMITS"
                    analysis.risk_budget = Decimal("1000")
                    analysis.max_position_notional = Decimal("5000")
            else:
                # Real risk evaluation
                pass

            if analysis.risk_decision == "APPROVED":
                run.candidates_approved += 1
            else:
                run.candidates_rejected += 1

            self._emit_event(
                self._current_run,
                CouncilRunEventType.RISK_DECISION,
                f"Risk decision for {analysis.symbol}: {analysis.risk_decision}",
                {"symbol": analysis.symbol, "decision": analysis.risk_decision},
            )

    async def _run_instrument_stage(self, run: CouncilRun) -> None:
        """Run M5 instrument selection stage."""
        for analysis in run.candidate_analyses:
            if analysis.risk_decision != "APPROVED":
                analysis.instrument_type = "NO_TRADE"
                continue

            if run.demo_mode:
                analysis.instrument_type = "STOCK"
                analysis.instrument_selection_reason = "Equity plan created with sufficient risk budget"
            else:
                # Real instrument selection
                pass

            self._emit_event(
                self._current_run,
                CouncilRunEventType.INSTRUMENT_SELECTED,
                f"Instrument selected for {analysis.symbol}: {analysis.instrument_type}",
                {"symbol": analysis.symbol, "type": analysis.instrument_type},
            )

    async def _run_execution_stage(self, run: CouncilRun) -> None:
        """Run M6 execution planning (dry run) stage."""
        for analysis in run.candidate_analyses:
            if analysis.instrument_type == "NO_TRADE":
                continue

            if run.demo_mode:
                analysis.execution_plan_id = f"exec-plan-{uuid4().hex[:8]}"
                analysis.execution_authorized = True
                analysis.dry_run = True
            else:
                # Real execution planning
                pass

            self._emit_event(
                self._current_run,
                CouncilRunEventType.EXECUTION_AUTHORIZED,
                f"Execution authorized for {analysis.symbol} (dry run)",
                {"symbol": analysis.symbol, "dry_run": analysis.dry_run},
            )

    def _create_demo_candidate_set(self) -> dict:
        """Create synthetic candidate set for demo mode."""
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "universe_mode": "curated",
            "universe_size": 64,
            "eligible_count": 12,
            "rejected_count": 52,
            "preliminary_count": 15,
            "deep_analysis_count": 8,
            "final_count": 5,
            "candidates": [
                {
                    "symbol": "SPY",
                    "rank": 1,
                    "direction": "BULLISH",
                    "opportunity_score": {"total": "82.5", "direction": "BULLISH"},
                },
                {
                    "symbol": "QQQ",
                    "rank": 2,
                    "direction": "BULLISH",
                    "opportunity_score": {"total": "78.3", "direction": "BULLISH"},
                },
                {
                    "symbol": "AAPL",
                    "rank": 3,
                    "direction": "BEARISH",
                    "opportunity_score": {"total": "75.1", "direction": "BEARISH"},
                },
                {
                    "symbol": "TSLA",
                    "rank": 4,
                    "direction": "BULLISH",
                    "opportunity_score": {"total": "71.2", "direction": "BULLISH"},
                },
                {
                    "symbol": "NVDA",
                    "rank": 5,
                    "direction": "BULLISH",
                    "opportunity_score": {"total": "69.8", "direction": "BULLISH"},
                },
            ],
            "rejections": [],
            "runtime_ms": 150,
        }

    def get_current_run(self) -> Optional[CouncilRun]:
        """Get the current run."""
        return self._current_run


def create_council_orchestrator(
    settings: Optional[Settings] = None,
    market_gateway: Optional["AlpacaMarketDataGateway"] = None,
    alpaca_gateway: Optional["AlpacaGateway"] = None,
    position_store: Optional["PositionStore"] = None,
    memory_service: Optional[TradingMemoryService] = None,
) -> CouncilOrchestrator:
    """Factory function to create council orchestrator."""
    return CouncilOrchestrator(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
        memory_service=memory_service,
    )