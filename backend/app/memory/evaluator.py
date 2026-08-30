"""Post-Trade Evaluator for M8.

Deterministic evaluation of closed positions into structured trade records.
ZERO LLM calls. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.committee.models import (
    AgentStance as M3AgentStance,
)
from app.committee.models import (
    CommitteeDecision,
    CommitteeResult,
    TradeThesis,
)
from app.execution.models import ExecutionResult
from app.instruments.models import InstrumentPlan
from app.memory.models import (
    DEFAULT_THESIS_MATERIALITY_THRESHOLD_PCT,
    AgentPerformanceRecord,
    AgentStance,
    ExecutionQualityEvaluation,
    ExitQualityEvaluation,
    InstrumentOutcomeEvaluation,
    RiskOutcomeEvaluation,
    ThesisCorrectness,
    ThesisOutcomeEvaluation,
    TradeOutcome,
    TradeOutcomeType,
    TradeRecord,
)
from app.positions.models import ExitReasonCode, ManagedPosition, PositionStatus
from app.risk.models import RiskEvaluation


class PostTradeEvaluator:
    """Evaluates closed ManagedPositions into structured TradeRecords."""

    def __init__(
        self,
        thesis_materiality_threshold_pct: Decimal = DEFAULT_THESIS_MATERIALITY_THRESHOLD_PCT,
    ) -> None:
        self.thesis_materiality_threshold_pct = thesis_materiality_threshold_pct

    def evaluate(
        self,
        position: ManagedPosition,
        committee_result: CommitteeResult | None = None,
        trade_thesis: TradeThesis | None = None,
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
        """Evaluate a closed position into all M8 components.

        Returns all evaluation components for persistence.
        """
        # Validate position is closed
        if position.status not in (PositionStatus.CLOSED, PositionStatus.EXIT_PENDING):
            raise ValueError(f"Position {position.position_id} is not closed: {position.status}")

        # Generate or reuse trade_id
        trade_id = self._get_or_create_trade_id(position)

        # Build TradeRecord
        trade_record = self._build_trade_record(
            trade_id, position, committee_result, trade_thesis,
            risk_evaluation, instrument_plan, entry_execution, exit_execution
        )

        # Build TradeOutcome
        trade_outcome = self._build_trade_outcome(trade_id, trade_record)

        # Build ThesisOutcomeEvaluation
        thesis_eval = self._build_thesis_evaluation(
            trade_id, position, trade_thesis, trade_record,
            underlying_entry_price, underlying_exit_price
        )

        # Build ExecutionQualityEvaluation
        exec_quality = self._build_execution_quality(
            trade_id, instrument_plan, entry_execution, exit_execution
        )

        # Build ExitQualityEvaluation
        exit_quality = self._build_exit_quality(trade_id, position, trade_record)

        # Build RiskOutcomeEvaluation
        risk_outcome = self._build_risk_outcome(trade_id, position, risk_evaluation, trade_record)

        # Build InstrumentOutcomeEvaluation
        instrument_outcome = self._build_instrument_outcome(trade_id, instrument_plan, trade_record)

        # Build AgentPerformanceRecords
        agent_records = self._build_agent_performance(
            trade_id, committee_result, trade_record, thesis_eval
        )

        return (
            trade_record,
            trade_outcome,
            thesis_eval,
            exec_quality,
            exit_quality,
            risk_outcome,
            instrument_outcome,
            agent_records,
        )

    def _get_or_create_trade_id(self, position: ManagedPosition) -> str:
        """Get stable trade_id from position_id."""
        return f"trade-{position.position_id}"

    def _build_trade_record(
        self,
        trade_id: str,
        position: ManagedPosition,
        committee_result: CommitteeResult | None,
        trade_thesis: TradeThesis | None,
        risk_evaluation: RiskEvaluation | None,
        instrument_plan: InstrumentPlan | None,
        entry_execution: ExecutionResult | None,
        exit_execution: ExecutionResult | None,
    ) -> TradeRecord:
        """Build the core TradeRecord."""
        # Calculate holding duration
        holding_duration = None
        exit_ts = getattr(position, 'exit_timestamp', None)
        if position.entry_timestamp and exit_ts:
            holding_duration = int((exit_ts - position.entry_timestamp).total_seconds())
        elif position.entry_timestamp:
            holding_duration = int((datetime.now(UTC) - position.entry_timestamp).total_seconds())

        # Determine exit reason codes
        exit_reasons = []
        if hasattr(position, 'exit_reason_codes') and position.exit_reason_codes:
            exit_reasons = [str(r) for r in position.exit_reason_codes]

        # Committee data
        committee_confidence = None
        committee_disagreement = None
        if committee_result:
            committee_confidence = committee_result.decision.committee_confidence
            committee_disagreement = committee_result.decision.final_disagreement.value

        # Instrument selection score
        instrument_score = None
        if instrument_plan:
            if instrument_plan.equity_plan:
                instrument_score = instrument_plan.equity_plan.selection_score
            elif instrument_plan.option_plan:
                instrument_score = instrument_plan.option_plan.selection_score

        # Risk decision
        risk_decision = None
        if risk_evaluation:
            risk_decision = risk_evaluation.decision.value

        # Calculate return_pct from entry/exit prices
        return_pct = None
        if position.entry_price and position.current_price and position.entry_price > 0:
            if position.side == "LONG":
                return_pct = (position.current_price - position.entry_price) / position.entry_price
            else:  # SHORT
                return_pct = (position.entry_price - position.current_price) / position.entry_price

        # Calculate r_multiple
        r_multiple = None
        initial_risk = None
        if risk_evaluation and risk_evaluation.risk_budget:
            initial_risk = risk_evaluation.risk_budget.adjusted_risk_budget
            if initial_risk and initial_risk > 0 and position.realized_pnl is not None:
                r_multiple = position.realized_pnl / initial_risk

        # Data quality flags
        data_quality_flags = []
        if not committee_result:
            data_quality_flags.append("MISSING_COMMITTEE")
        if not trade_thesis:
            data_quality_flags.append("MISSING_THESIS")
        if not risk_evaluation:
            data_quality_flags.append("MISSING_RISK_EVAL")
        if not instrument_plan:
            data_quality_flags.append("MISSING_INSTRUMENT_PLAN")
        if not entry_execution:
            data_quality_flags.append("MISSING_ENTRY_EXECUTION")
        if not exit_execution:
            data_quality_flags.append("MISSING_EXIT_EXECUTION")

        return TradeRecord(
            trade_id=trade_id,
            candidate_id=getattr(committee_result, 'candidate_symbol', None) if committee_result else None,
            committee_result_id=getattr(committee_result, 'decision', None) and getattr(committee_result.decision, 'symbol', None) if committee_result else None,
            trade_thesis_id=trade_thesis.summary[:50] if trade_thesis else None,
            risk_evaluation_id=risk_evaluation.symbol if risk_evaluation else None,
            instrument_plan_id=instrument_plan.plan_id if instrument_plan else None,
            entry_execution_id=entry_execution.execution_plan_id if entry_execution else None,
            position_id=position.position_id,
            exit_execution_id=exit_execution.execution_plan_id if exit_execution else None,
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            direction=position.side,
            discovery_timestamp=None,  # Not available from position alone
            thesis_timestamp=trade_thesis.market_state_as_of if trade_thesis else None,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=exit_ts or datetime.now(UTC),
            entry_price=position.entry_price,
            exit_price=position.current_price,  # Use current_price as exit price
            entry_quantity=position.initial_quantity,
            exit_quantity=position.current_quantity,
            entry_notional=position.initial_notional,
            exit_notional=position.current_notional,
            realized_pnl=position.realized_pnl,
            return_pct=return_pct,
            holding_duration_seconds=holding_duration,
            mfe_amount=None,  # Calculated from position metrics
            mfe_pct=position.mfe if position.mfe else None,
            mfe_r_multiple=None,
            mae_amount=None,
            mae_pct=position.mae if position.mae else None,
            mae_r_multiple=None,
            initial_risk_amount=initial_risk,
            r_multiple=r_multiple,
            risk_budget=risk_evaluation.risk_budget.base_risk_budget if risk_evaluation and risk_evaluation.risk_budget else None,
            max_position_notional=risk_evaluation.risk_budget.max_position_notional if risk_evaluation and risk_evaluation.risk_budget else None,
            initial_stop=position.initial_stop_reference,
            exit_reason_codes=tuple(exit_reasons),
            committee_confidence=committee_confidence,
            committee_disagreement=committee_disagreement,
            instrument_selection_score=instrument_score,
            risk_decision=risk_decision,
            constitution_version=position.constitution_version,
            data_quality_flags=tuple(data_quality_flags),
        )

    def _build_trade_outcome(self, trade_id: str, trade_record: TradeRecord) -> TradeOutcome:
        """Build TradeOutcome from TradeRecord."""
        realized_pnl = trade_record.realized_pnl
        return_pct = trade_record.return_pct
        r_multiple = trade_record.r_multiple

        # Determine outcome type
        if realized_pnl is None:
            outcome_type = TradeOutcomeType.UNKNOWN
        elif realized_pnl > Decimal("0"):
            outcome_type = TradeOutcomeType.WIN
        elif realized_pnl < Decimal("0"):
            outcome_type = TradeOutcomeType.LOSS
        else:
            outcome_type = TradeOutcomeType.BREAKEVEN

        # Calculate R multiple if not present
        if r_multiple is None and trade_record.initial_risk_amount and trade_record.realized_pnl:
            if trade_record.initial_risk_amount > 0:
                r_multiple = trade_record.realized_pnl / trade_record.initial_risk_amount

        return TradeOutcome(
            trade_id=trade_id,
            outcome_type=outcome_type,
            realized_pnl=realized_pnl,
            return_pct=return_pct,
            r_multiple=r_multiple,
            mfe_pct=trade_record.mfe_pct,
            mae_pct=trade_record.mae_pct,
            holding_duration_seconds=trade_record.holding_duration_seconds,
        )

    def _build_thesis_evaluation(
        self,
        trade_id: str,
        position: ManagedPosition,
        trade_thesis: TradeThesis | None,
        trade_record: TradeRecord,
        underlying_entry_price: Decimal | None,
        underlying_exit_price: Decimal | None,
    ) -> ThesisOutcomeEvaluation:
        """Evaluate directional thesis correctness (SEPARATE from profitability)."""
        # Use provided underlying prices or fall back to position prices
        entry_price = underlying_entry_price or position.entry_price
        exit_price = underlying_exit_price or position.current_price

        if not entry_price or not exit_price or entry_price <= 0:
            return ThesisOutcomeEvaluation(
                trade_id=trade_id,
                correctness=ThesisCorrectness.INCONCLUSIVE,
                rationale="Insufficient price data for thesis evaluation",
                materiality_threshold_pct=self.thesis_materiality_threshold_pct,
            )

        # Calculate underlying move: positive = price went up, negative = price went down
        underlying_move_pct = (exit_price - entry_price) / entry_price

        # Determine thesis direction from committee
        thesis_bullish = True
        if trade_thesis:
            thesis_bullish = trade_thesis.proposed_direction.value in ("BULLISH", "STRONG_LONG", "LONG")
        elif position.side == "LONG":
            thesis_bullish = True
        else:
            thesis_bullish = False

        # Evaluate correctness
        materiality = self.thesis_materiality_threshold_pct

        if abs(underlying_move_pct) < materiality:
            correctness = ThesisCorrectness.INCONCLUSIVE
            rationale = f"Underlying move {underlying_move_pct:.2%} below materiality threshold {materiality:.2%}"
        elif (underlying_move_pct > 0 and thesis_bullish) or (underlying_move_pct < 0 and not thesis_bullish):
            # Direction matches thesis
            if abs(underlying_move_pct) >= materiality * 2:
                correctness = ThesisCorrectness.CORRECT
            else:
                correctness = ThesisCorrectness.PARTIALLY_CORRECT
            rationale = f"Thesis direction correct. Underlying moved {underlying_move_pct:.2%} in expected direction."
        else:
            # Direction wrong
            correctness = ThesisCorrectness.INCORRECT
            rationale = f"Thesis direction incorrect. Underlying moved {underlying_move_pct:.2%} opposite to expected."

        return ThesisOutcomeEvaluation(
            trade_id=trade_id,
            correctness=correctness,
            underlying_entry_price=entry_price,
            underlying_exit_price=exit_price,
            underlying_move_pct=underlying_move_pct,
            materiality_threshold_pct=self.thesis_materiality_threshold_pct,
            rationale=rationale,
        )

    def _build_execution_quality(
        self,
        trade_id: str,
        instrument_plan: InstrumentPlan | None,
        entry_execution: ExecutionResult | None,
        exit_execution: ExecutionResult | None,
    ) -> ExecutionQualityEvaluation:
        """Evaluate execution quality for entry and exit."""
        # Entry quality
        entry_planned = None
        entry_actual = None
        if instrument_plan and instrument_plan.equity_plan:
            entry_planned = instrument_plan.equity_plan.reference_price
        if entry_execution and entry_execution.execution_order:
            entry_actual = entry_execution.execution_order.filled_avg_price

        entry_slippage_amount = None
        entry_slippage_pct = None
        if entry_planned and entry_actual and entry_planned > 0:
            entry_slippage_amount = entry_actual - entry_planned
            entry_slippage_pct = entry_slippage_amount / entry_planned

        # Exit quality
        exit_planned = None
        exit_actual = None
        if exit_execution and exit_execution.execution_order:
            exit_actual = exit_execution.execution_order.filled_avg_price
        # Exit planned price would come from exit plan - not available here

        exit_slippage_amount = None
        exit_slippage_pct = None
        if exit_planned and exit_actual and exit_planned > 0:
            exit_slippage_amount = exit_actual - exit_planned
            exit_slippage_pct = exit_slippage_amount / exit_planned

        return ExecutionQualityEvaluation(
            trade_id=trade_id,
            entry_planned_price=entry_planned,
            entry_actual_price=entry_actual,
            entry_slippage_amount=entry_slippage_amount,
            entry_slippage_pct=entry_slippage_pct,
            exit_planned_price=exit_planned,
            exit_actual_price=exit_actual,
            exit_slippage_amount=exit_slippage_amount,
            exit_slippage_pct=exit_slippage_pct,
        )

    def _build_exit_quality(
        self,
        trade_id: str,
        position: ManagedPosition,
        trade_record: TradeRecord,
    ) -> ExitQualityEvaluation:
        """Evaluate exit quality (captured profit ratio, giveback)."""
        mfe_pct = position.mfe
        realized_return = trade_record.return_pct

        captured_profit_ratio = None
        giveback_from_mfe = None

        if mfe_pct and realized_return and mfe_pct > 0:
            # For LONG: MFE is positive, realized_return positive means profit captured
            # For SHORT: MFE is positive (adverse), realized_return negative means profit
            if position.side == "LONG":
                if realized_return > 0:
                    captured_profit_ratio = realized_return / mfe_pct
                    giveback_from_mfe = (mfe_pct - realized_return) / mfe_pct
            else:  # SHORT
                if realized_return < 0:
                    captured_profit_ratio = abs(realized_return) / mfe_pct
                    giveback_from_mfe = (mfe_pct - abs(realized_return)) / mfe_pct

        return ExitQualityEvaluation(
            trade_id=trade_id,
            mfe_pct=mfe_pct,
            realized_return_pct=realized_return,
            captured_profit_ratio=captured_profit_ratio,
            giveback_from_mfe_pct=giveback_from_mfe,
        )

    def _build_risk_outcome(
        self,
        trade_id: str,
        position: ManagedPosition,
        risk_evaluation: RiskEvaluation | None,
        trade_record: TradeRecord,
    ) -> RiskOutcomeEvaluation:
        """Evaluate risk outcome."""
        authorized_risk = None
        if risk_evaluation and risk_evaluation.risk_budget:
            authorized_risk = risk_evaluation.risk_budget.adjusted_risk_budget

        realized_loss = None
        if trade_record.realized_pnl and trade_record.realized_pnl < 0:
            realized_loss = abs(trade_record.realized_pnl)

        mae_amount = None
        if position.mae and position.entry_price and position.initial_quantity:
            mae_amount = position.mae * position.entry_price * position.initial_quantity

        risk_utilization = None
        if authorized_risk and realized_loss and authorized_risk > 0:
            risk_utilization = realized_loss / authorized_risk

        # Check exit reason codes for triggers
        exit_reasons = trade_record.exit_reason_codes
        hard_stop = ExitReasonCode.HARD_STOP_TRIGGERED.value in exit_reasons
        kill_switch = ExitReasonCode.KILL_SWITCH.value in exit_reasons
        max_loss = ExitReasonCode.MAX_LOSS_REACHED.value in exit_reasons

        m4_reduced = risk_evaluation.is_reduced if risk_evaluation else False
        reduction_reason = None
        if m4_reduced and risk_evaluation:
            reduction_reason = risk_evaluation.get_primary_reason().value

        loss_within_authorized = None
        if authorized_risk and realized_loss is not None:
            loss_within_authorized = realized_loss <= authorized_risk

        return RiskOutcomeEvaluation(
            trade_id=trade_id,
            authorized_risk=authorized_risk,
            realized_loss=realized_loss,
            mae_amount=mae_amount,
            risk_utilization_pct=risk_utilization,
            hard_stop_triggered=hard_stop,
            kill_switch_triggered=kill_switch,
            max_loss_triggered=max_loss,
            m4_reduced_exposure=m4_reduced,
            reduction_reason=reduction_reason,
            loss_within_authorized=loss_within_authorized,
        )

    def _build_instrument_outcome(
        self,
        trade_id: str,
        instrument_plan: InstrumentPlan | None,
        trade_record: TradeRecord,
    ) -> InstrumentOutcomeEvaluation:
        """Evaluate instrument outcome."""
        instrument_type = "UNKNOWN"
        selection_score = None

        if instrument_plan:
            instrument_type = instrument_plan.instrument_type.value
            if instrument_plan.equity_plan:
                selection_score = instrument_plan.equity_plan.selection_score
            elif instrument_plan.option_plan:
                selection_score = instrument_plan.option_plan.selection_score

        trade_outcome = None
        if trade_record.realized_pnl is not None:
            if trade_record.realized_pnl > 0:
                trade_outcome = TradeOutcomeType.WIN
            elif trade_record.realized_pnl < 0:
                trade_outcome = TradeOutcomeType.LOSS
            else:
                trade_outcome = TradeOutcomeType.BREAKEVEN

        return InstrumentOutcomeEvaluation(
            trade_id=trade_id,
            instrument_type=instrument_type,
            selection_score=selection_score,
            trade_outcome=trade_outcome,
        )

    def _build_agent_performance(
        self,
        trade_id: str,
        committee_result: CommitteeResult | None,
        trade_record: TradeRecord,
        thesis_eval: ThesisOutcomeEvaluation,
    ) -> list[AgentPerformanceRecord]:
        """Build agent performance records from committee result."""
        if not committee_result:
            return []

        records = []
        final_opinions = committee_result.final_opinions or committee_result.initial_opinions or ()

        # Determine committee direction
        committee_direction = None
        if committee_result.decision.decision == CommitteeDecision.PROPOSE_LONG:
            committee_direction = "LONG"
        elif committee_result.decision.decision == CommitteeDecision.PROPOSE_SHORT:
            committee_direction = "SHORT"

        # Trade profitability
        trade_profitable = None
        if trade_record.realized_pnl is not None:
            trade_profitable = trade_record.realized_pnl > 0

        for opinion in final_opinions:
            # Map M3 stance to M8 stance
            stance = self._map_stance(opinion.stance)

            # Direction correctness
            direction_correct = None
            calibration_target = None
            if thesis_eval.correctness != ThesisCorrectness.INCONCLUSIVE:
                if opinion.stance in (M3AgentStance.STRONG_LONG, M3AgentStance.LONG):
                    direction_correct = thesis_eval.correctness in (ThesisCorrectness.CORRECT, ThesisCorrectness.PARTIALLY_CORRECT)
                    calibration_target = 1 if direction_correct else 0
                elif opinion.stance in (M3AgentStance.STRONG_SHORT, M3AgentStance.SHORT):
                    direction_correct = thesis_eval.correctness in (ThesisCorrectness.CORRECT, ThesisCorrectness.PARTIALLY_CORRECT)
                    calibration_target = 1 if direction_correct else 0
                elif opinion.stance == M3AgentStance.ABSTAIN:
                    # Abstaining agents are NOT scored as incorrect
                    direction_correct = None
                    calibration_target = None
                else:  # NEUTRAL
                    direction_correct = thesis_eval.correctness is ThesisCorrectness.INCONCLUSIVE
                    calibration_target = 1 if direction_correct else 0

            # Committee agreement
            committee_agreement = None
            if committee_direction and opinion.is_directional:
                if opinion.is_bullish and committee_direction == "LONG":
                    committee_agreement = True
                elif opinion.is_bearish and committee_direction == "SHORT":
                    committee_agreement = True
                else:
                    committee_agreement = False

            records.append(AgentPerformanceRecord(
                trade_id=trade_id,
                agent_name=opinion.agent_role.value,
                stance=stance,
                confidence=opinion.confidence,
                participated=opinion.stance != M3AgentStance.ABSTAIN,
                abstained=opinion.stance == M3AgentStance.ABSTAIN,
                supporting_evidence_ids=opinion.supporting_evidence_ids,
                contradicting_evidence_ids=opinion.contradicting_evidence_ids,
                direction_correct=direction_correct,
                calibration_target=calibration_target,
                committee_agreement=committee_agreement,
                trade_profitable=trade_profitable,
                r_multiple=trade_record.r_multiple,
            ))

        return records

    def _map_stance(self, m3_stance: M3AgentStance) -> AgentStance:
        """Map M3 AgentStance to M8 AgentStance."""
        mapping = {
            M3AgentStance.STRONG_LONG: AgentStance.STRONG_LONG,
            M3AgentStance.LONG: AgentStance.LONG,
            M3AgentStance.NEUTRAL: AgentStance.NEUTRAL,
            M3AgentStance.SHORT: AgentStance.SHORT,
            M3AgentStance.STRONG_SHORT: AgentStance.STRONG_SHORT,
            M3AgentStance.ABSTAIN: AgentStance.ABSTAIN,
        }
        return mapping.get(m3_stance, AgentStance.NEUTRAL)


def create_post_trade_evaluator(
    thesis_materiality_threshold_pct: Decimal = DEFAULT_THESIS_MATERIALITY_THRESHOLD_PCT,
) -> PostTradeEvaluator:
    """Factory function to create post-trade evaluator."""
    return PostTradeEvaluator(thesis_materiality_threshold_pct)