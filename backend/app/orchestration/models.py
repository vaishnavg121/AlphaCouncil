"""CouncilRun orchestration models for M9 end-to-end pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.committee.models import CommitteeResult
from app.execution.models import ExecutionPlan, ExecutionReasonCode, ExecutionStatus
from app.instruments.models import InstrumentPlan
from app.risk.models import RiskEvaluation


class CouncilRunStatus(StrEnum):
    """Council run lifecycle status."""

    STARTED = "STARTED"
    DISCOVERING = "DISCOVERING"
    COMMITTEE = "COMMITTEE"
    RISK = "RISK"
    INSTRUMENT = "INSTRUMENT"
    EXECUTION_PLANNING = "EXECUTION_PLANNING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class CouncilRunEventType(StrEnum):
    """Event types for streaming."""

    RUN_STARTED = "run_started"
    MARKET_SCAN_STARTED = "market_scan_started"
    CANDIDATE_FOUND = "candidate_found"
    COMMITTEE_STARTED = "committee_started"
    AGENT_COMPLETED = "agent_completed"
    COMMITTEE_COMPLETED = "committee_completed"
    RISK_EVALUATION_STARTED = "risk_evaluation_started"
    RISK_DECISION = "risk_decision"
    INSTRUMENT_SELECTION_STARTED = "instrument_selection_started"
    INSTRUMENT_SELECTED = "instrument_selected"
    EXECUTION_DRY_RUN_STARTED = "execution_dry_run_started"
    EXECUTION_AUTHORIZED = "execution_authorized"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class CouncilRunEvent(BaseModel):
    """Streaming event for council run progress."""

    model_config = ConfigDict(frozen=True)

    event_type: CouncilRunEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_id: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class CandidateAnalysis(BaseModel):
    """Analysis result for a single candidate through the pipeline."""

    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    candidate_rank: int | None = None
    opportunity_score: Decimal | None = None
    direction: str | None = None
    opportunity: dict[str, Any] = Field(default_factory=dict)

    # M3 Committee
    committee_result_id: str | None = None
    committee_result: CommitteeResult | None = None
    committee_decision: str | None = None
    committee_confidence: Decimal | None = None
    committee_disagreement: str | None = None
    agent_opinions: dict[str, Any] = Field(default_factory=dict)

    # M4 Risk
    risk_evaluation_id: str | None = None
    risk_evaluation: RiskEvaluation | None = None
    risk_decision: str | None = None
    risk_reason: str | None = None
    risk_budget: Decimal | None = None
    max_position_notional: Decimal | None = None

    # M5 Instrument
    instrument_plan: InstrumentPlan | None = None
    instrument_type: str | None = None
    instrument_selection_reason: str | None = None

    # M6 Execution
    execution_plan_id: str | None = None
    execution_plan: ExecutionPlan | None = None
    execution_authorized: bool = False
    execution_status: ExecutionStatus = ExecutionStatus.NOT_EXECUTED
    execution_reason_codes: tuple[ExecutionReasonCode, ...] = ()
    dry_run: bool = True

    # Status
    status: str = "PENDING"
    stop_reason_codes: tuple[str, ...] = ()
    error: str | None = None


class CouncilRun(BaseModel):
    """Complete end-to-end council run record."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    status: CouncilRunStatus = CouncilRunStatus.STARTED

    # Configuration
    demo_mode: bool = False
    max_candidates: int = 10

    # Pipeline results
    candidate_set: dict[str, Any] | None = None  # M2 CandidateSet
    candidate_analyses: list[CandidateAnalysis] = Field(default_factory=list)

    # Summary
    candidates_discovered: int = 0
    candidates_analyzed: int = 0
    candidates_approved: int = 0
    candidates_rejected: int = 0

    # Errors
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Timing
    total_runtime_ms: int = 0
    stage_timings: dict[str, int] = Field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            CouncilRunStatus.COMPLETE,
            CouncilRunStatus.PARTIAL,
            CouncilRunStatus.FAILED,
        )

    @property
    def success_rate(self) -> float:
        if self.candidates_analyzed == 0:
            return 0.0
        return self.candidates_approved / self.candidates_analyzed


class CouncilRunRequest(BaseModel):
    """Request to start a council run."""

    model_config = ConfigDict(frozen=True)

    max_candidates: int = 10
    demo_mode: bool = False
    universe_mode: str | None = None  # "curated" | "alpaca"
    symbols: list[str] | None = None


class CouncilRunResponse(BaseModel):
    """Response for council run initiation."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: CouncilRunStatus
    message: str


def create_council_run(request: CouncilRunRequest) -> CouncilRun:
    """Factory function to create a new council run."""
    return CouncilRun(
        max_candidates=request.max_candidates,
        demo_mode=request.demo_mode,
    )
