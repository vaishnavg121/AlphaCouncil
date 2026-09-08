"""Trading Memory Service - Main API for M8 memory operations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.committee.models import CommitteeResult
from app.execution.models import ExecutionResult
from app.instruments.models import InstrumentPlan
from app.memory.analytics import (
    AnalyticsService,
    HistoricalContextProvider,
)
from app.memory.evaluator import create_post_trade_evaluator
from app.memory.models import (
    AgentPerformanceRecord,
    CalibrationSummary,
    ExecutionQualityEvaluation,
    ExitQualityEvaluation,
    HistoricalContext,
    InstrumentOutcomeEvaluation,
    PerformanceSummary,
    RiskOutcomeEvaluation,
    SimilarTradeResult,
    ThesisOutcomeEvaluation,
    TradeOutcome,
    TradeRecord,
)
from app.memory.store import TradingMemoryStore, create_trading_memory_store
from app.positions.models import ManagedPosition
from app.positions.store import PositionStore
from app.risk.models import RiskEvaluation

if TYPE_CHECKING:
    from app.positions.models import PositionStoreRecord


class TradingMemoryService:
    """Main service for trading memory operations."""

    def __init__(
        self,
        memory_store: TradingMemoryStore | None = None,
        position_store: PositionStore | None = None,
        thesis_materiality_threshold_pct: Decimal = Decimal("0.02"),
    ) -> None:
        self.memory_store = memory_store or create_trading_memory_store()
        self.position_store = position_store
        self.evaluator = create_post_trade_evaluator(thesis_materiality_threshold_pct)
        self.context_provider = HistoricalContextProvider(self.memory_store)
        self.analytics_service = AnalyticsService(self.memory_store)

    def evaluate_closed_position(
        self,
        position: ManagedPosition,
        committee_result: CommitteeResult | None = None,
        trade_thesis: Any = None,
        risk_evaluation: RiskEvaluation | None = None,
        instrument_plan: InstrumentPlan | None = None,
        entry_execution: ExecutionResult | None = None,
        exit_execution: ExecutionResult | None = None,
        underlying_entry_price: Decimal | None = None,
        underlying_exit_price: Decimal | None = None,
    ) -> tuple[
        TradeRecord,
        TradeOutcome,
        ThesisOutcomeEvaluation,
        ExecutionQualityEvaluation,
        ExitQualityEvaluation,
        RiskOutcomeEvaluation,
        InstrumentOutcomeEvaluation,
        list[AgentPerformanceRecord],
    ]:
        """Evaluate a closed position and persist all components.

        Idempotent: evaluating the same position multiple times updates
        the existing record rather than creating duplicates.
        """
        # Check if already evaluated
        existing = self.memory_store.get_trade_record_by_position_id(position.position_id)
        if existing:
            # Update existing record with new data
            trade_record = existing.with_update(
                exit_timestamp=getattr(position, 'exit_timestamp', None) or datetime.now(UTC),
                exit_price=position.current_price,
                exit_quantity=position.current_quantity,
                exit_notional=position.current_notional,
                realized_pnl=position.realized_pnl,
                return_pct=position.unrealized_pnl_pct,
                mfe_pct=position.mfe,
                mae_pct=position.mae,
                # Version will be incremented in with_update
            )
        else:
            trade_record = None

        # Run full evaluation
        (
            new_trade_record,
            trade_outcome,
            thesis_eval,
            exec_quality,
            exit_quality,
            risk_outcome,
            instrument_outcome,
            agent_records,
        ) = self.evaluator.evaluate(
            position=position,
            committee_result=committee_result,
            trade_thesis=trade_thesis,
            risk_evaluation=risk_evaluation,
            instrument_plan=instrument_plan,
            entry_execution=entry_execution,
            exit_execution=exit_execution,
            underlying_entry_price=underlying_entry_price,
            underlying_exit_price=underlying_exit_price,
        )

        # If existing, preserve trade_id and merge
        if trade_record:
            new_trade_record = new_trade_record.model_copy(update={
                "trade_id": trade_record.trade_id,
                "created_at": trade_record.created_at,
                "version": trade_record.version + 1,
            })

        # Persist all components
        self.memory_store.upsert_trade_record(new_trade_record)
        self.memory_store.upsert_trade_outcome(trade_outcome)
        self.memory_store.upsert_thesis_evaluation(thesis_eval)
        self.memory_store.upsert_execution_quality(exec_quality)
        self.memory_store.upsert_exit_quality(exit_quality)
        self.memory_store.upsert_risk_outcome(risk_outcome)
        self.memory_store.upsert_instrument_outcome(instrument_outcome)

        for agent_rec in agent_records:
            self.memory_store.upsert_agent_performance(agent_rec)

        return (
            new_trade_record,
            trade_outcome,
            thesis_eval,
            exec_quality,
            exit_quality,
            risk_outcome,
            instrument_outcome,
            agent_records,
        )

    def get_trade(self, trade_id: str) -> TradeRecord | None:
        """Get trade record by ID."""
        return self.memory_store.get_trade_record(trade_id)

    def get_recent_trades(self, limit: int = 100) -> list[TradeRecord]:
        """Get recent trade records."""
        return self.memory_store.get_recent_trades(limit)

    def get_similar_trades(
        self,
        query_context: dict[str, Any],
        k: int = 10,
    ) -> list[SimilarTradeResult]:
        """Get similar historical trades."""
        all_trades = self.memory_store.get_all_trade_records()
        return self.context_provider.similarity_engine.find_similar(query_context, all_trades, k)

    def get_performance_summary(self) -> PerformanceSummary:
        """Get comprehensive performance summary."""
        return self.analytics_service.get_performance_summary()

    def get_committee_calibration(self) -> CalibrationSummary | None:
        """Get committee calibration analysis."""
        return self.analytics_service._compute_overall_calibration()  # type: ignore[return-value]

    def get_agent_performance(self, agent_name: str) -> list[AgentPerformanceRecord]:
        """Get all performance records for an agent."""
        return self.memory_store.get_agent_history(agent_name)

    def get_disagreement_stats(self) -> tuple[Any, ...]:
        """Get disagreement analytics."""
        all_trades = self.memory_store.get_all_trade_records()
        completed = [t for t in all_trades if t.is_complete]
        return self.analytics_service._compute_disagreement_analytics(completed)

    def get_exit_reason_stats(self) -> tuple[Any, ...]:
        """Get exit reason analytics."""
        all_trades = self.memory_store.get_all_trade_records()
        completed = [t for t in all_trades if t.is_complete]
        return self.analytics_service._compute_exit_reason_analytics(completed)

    def get_historical_context(self, query_context: dict[str, Any], k: int = 10) -> HistoricalContext:
        """Get historical context for a prospective trade."""
        return self.context_provider.get_context_for_trade(query_context, k)

    def recompute_calibration(self) -> CalibrationSummary:
        """Recompute and persist calibration from all agent data."""
        calibration = self.analytics_service._compute_overall_calibration()
        self.memory_store.save_calibration_snapshot(calibration)
        return calibration

    def close(self) -> None:
        """Close connections."""
        self.memory_store.close()


def create_trading_memory_service(
    db_path: str | None = None,
    position_store: PositionStore | None = None,
    thesis_materiality_threshold_pct: Decimal = Decimal("0.02"),
) -> TradingMemoryService:
    """Factory function to create trading memory service."""
    memory_store = create_trading_memory_store(db_path) if db_path else create_trading_memory_store()
    return TradingMemoryService(
        memory_store=memory_store,
        position_store=position_store,
        thesis_materiality_threshold_pct=thesis_materiality_threshold_pct,
    )