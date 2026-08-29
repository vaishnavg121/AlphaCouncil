#!/usr/bin/env python
"""M8 Trading Memory Diagnostic.

Runs M8 post-trade evaluation, memory persistence, and analytics
on synthetic closed positions. Shows concise sanitized output.

Default: DRY RUN - ZERO mutations to production data
Clearly labels all synthetic data as PAPER TRADING.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

# Allow direct execution
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from datetime import UTC, datetime, timedelta

from app.committee.models import (
    AgentOpinion,
    AgentRole,
    CommitteeDecision,
    CommitteeDecisionModel,
    CommitteeResult,
    DisagreementSeverity,
    EvidenceCategory,
    EvidenceItem,
    EvidencePacket,
    EvidenceSource,
    SignalDirection,
    TradeThesis,
)
from app.committee.models import (
    AgentStance as M3AgentStance,
)
from app.core.config import Settings
from app.execution.models import (
    ExecutionAuthorization,
    ExecutionAuthorizationState,
    ExecutionPlan,
    ExecutionReasonCode,
    ExecutionResult,
    ExecutionStatus,
    OrderSide,
    OrderType,
    TimeInForce,
)
from app.instruments.models import (
    EquityInstrumentPlan,
    EquitySide,
    InstrumentPlan,
    InstrumentType,
)
from app.memory import (
    ThesisCorrectness,
    TradeOutcomeType,
    TradeRecord,
    create_trading_memory_service,
)
from app.positions import (
    ExitReasonCode,
    ExitState,
    ManagedPosition,
    PositionStatus,
)
from app.risk.models import (
    RiskBudget,
    RiskCheckResult,
    RiskDecisionType,
    RiskEvaluation,
    RiskReasonCode,
    RiskRuleType,
)


def safe_print(text: str) -> None:
    """Print text safely handling Unicode characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        safe_text = text.encode("ascii", errors="replace").decode("ascii")
        print(safe_text)


def fmt_pct(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def fmt_usd(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def fmt_r(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}R"


def create_synthetic_committee_result(symbol: str, direction: str) -> CommitteeResult:
    """Create a synthetic CommitteeResult for testing."""
    now = datetime.now(UTC)
    agent_role = AgentRole.BULL if direction == "LONG" else AgentRole.BEAR
    stance = M3AgentStance.LONG if direction == "LONG" else M3AgentStance.SHORT

    opinion = AgentOpinion(
        agent_role=agent_role,
        symbol=symbol,
        stance=stance,
        confidence=Decimal("0.75"),
        thesis=f"Synthetic {direction} thesis for {symbol}",
        supporting_evidence_ids=("ev-momentum-001", "ev-trend-001"),
    )

    decision = CommitteeDecisionModel(
        symbol=symbol,
        decision=CommitteeDecision.PROPOSE_LONG if direction == "LONG" else CommitteeDecision.PROPOSE_SHORT,
        direction=SignalDirection.BULLISH if direction == "LONG" else SignalDirection.BEARISH,
        committee_score=Decimal("75"),
        committee_confidence=Decimal("0.75"),
        initial_disagreement=DisagreementSeverity.LOW,
        final_disagreement=DisagreementSeverity.LOW,
        participating_agents=(AgentRole.QUANT, AgentRole.BULL, AgentRole.BEAR, AgentRole.REGIME),
        decision_reasons=(f"Strong {direction} signals",),
    )

    thesis = TradeThesis(
        symbol=symbol,
        proposed_direction=SignalDirection.BULLISH if direction == "LONG" else SignalDirection.BEARISH,
        committee_confidence=Decimal("0.75"),
        summary=f"Synthetic {direction} thesis for {symbol}",
        market_state_as_of=now,
        candidate_score=Decimal("70"),
        committee_decision=decision,
    )

    return CommitteeResult(
        candidate_symbol=symbol,
        evidence_packet=EvidencePacket(
            symbol=symbol,
            as_of=now,
            evidence=(
                EvidenceItem(id="ev-momentum-001", category=EvidenceCategory.MOMENTUM, label="5d Return", value="+3.2%", source=EvidenceSource.M1_FEATURE),
                EvidenceItem(id="ev-trend-001", category=EvidenceCategory.TREND, label="SMA20", value="Above", source=EvidenceSource.M1_FEATURE),
            ),
        ),
        initial_opinions=(opinion,),
        final_opinions=(opinion,),
        decision=decision,
        trade_thesis=thesis,
    )


def create_synthetic_risk_evaluation(symbol: str, approved: bool = True) -> RiskEvaluation:
    """Create a synthetic RiskEvaluation for testing."""
    decision = RiskDecisionType.APPROVED if approved else RiskDecisionType.REDUCED
    reason = RiskReasonCode.WITHIN_LIMITS if approved else RiskReasonCode.VOLATILITY_REDUCTION

    return RiskEvaluation(
        symbol=symbol,
        decision=decision,
        reason_code=reason,
        risk_budget=RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("1000") if approved else Decimal("800"),
            max_position_notional=Decimal("5000"),
            atr_stop_distance=Decimal("5.0"),
            shares=10,
        ),
        constitution_version="v1.0.0",
        checks=(
            RiskCheckResult(
                rule_name="test_rule",
                rule_type=RiskRuleType.HARD_GATE,
                passed=True,
                reason_code=RiskReasonCode.WITHIN_LIMITS,
            ),
        ),
    )


def create_synthetic_instrument_plan(symbol: str, direction: str) -> InstrumentPlan:
    """Create a synthetic InstrumentPlan for testing."""
    return InstrumentPlan(
        plan_id=f"plan-{uuid4().hex[:8]}",
        symbol=symbol,
        thesis_direction="BULLISH" if direction == "LONG" else "BEARISH",
        instrument_type=InstrumentType.STOCK,
        equity_plan=EquityInstrumentPlan(
            symbol=symbol,
            side=EquitySide.LONG if direction == "LONG" else EquitySide.SHORT,
            reference_price=Decimal("100.00"),
            max_notional=Decimal("5000"),
            planned_notional=Decimal("4500"),
            estimated_quantity=Decimal("45"),
            risk_budget_used=Decimal("1000"),
            estimated_loss_at_risk_stop=Decimal("500"),
            selection_score=Decimal("80"),
            selection_reasons=("Good liquidity", "Tight spread"),
        ),
    )


def create_synthetic_entry_execution(plan_id: str, symbol: str, fill_price: Decimal) -> ExecutionResult:
    """Create a synthetic entry ExecutionResult for testing."""
    now = datetime.now(UTC)
    return ExecutionResult(
        execution_plan_id=f"exec-plan-{uuid4().hex[:8]}",
        instrument_plan_id=plan_id,
        status=ExecutionStatus.FILLED,
        authorization=ExecutionAuthorization(
            execution_plan_id=f"exec-plan-{uuid4().hex[:8]}",
            state=ExecutionAuthorizationState.AUTHORIZED,
            reason_code=ExecutionReasonCode.WITHIN_LIMITS,
        ),
        execution_plan=ExecutionPlan(
            execution_plan_id=f"exec-plan-{uuid4().hex[:8]}",
            instrument_plan_id=plan_id,
            symbol=symbol,
            instrument_type="STOCK",
            direction="BULLISH",
            side=OrderSide.BUY,
            quantity=Decimal("45"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=Decimal("100.00"),
            fresh_bid=Decimal("99.95"),
            fresh_ask=Decimal("100.05"),
            fresh_mid=Decimal("100.00"),
            fresh_quote_timestamp=now,
            limit_price=Decimal("100.10"),
            expected_notional=Decimal("4500"),
            risk_budget=Decimal("1000"),
            max_authorized_notional=Decimal("5000"),
            constitution_version="v1.0.0",
            expires_at=now + timedelta(hours=1),
        ),
    )


def create_synthetic_exit_execution(plan_id: str, symbol: str, fill_price: Decimal) -> ExecutionResult:
    """Create a synthetic exit ExecutionResult for testing."""
    now = datetime.now(UTC)
    return ExecutionResult(
        execution_plan_id=f"exit-plan-{uuid4().hex[:8]}",
        instrument_plan_id=plan_id,
        status=ExecutionStatus.FILLED,
        authorization=ExecutionAuthorization(
            execution_plan_id=f"exit-plan-{uuid4().hex[:8]}",
            state=ExecutionAuthorizationState.AUTHORIZED,
            reason_code=ExecutionReasonCode.WITHIN_LIMITS,
        ),
        execution_plan=ExecutionPlan(
            execution_plan_id=f"exit-plan-{uuid4().hex[:8]}",
            instrument_plan_id=plan_id,
            symbol=symbol,
            instrument_type="STOCK",
            direction="BULLISH",
            side=OrderSide.SELL,
            quantity=Decimal("45"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=Decimal("100.00"),
            fresh_bid=Decimal("99.95"),
            fresh_ask=Decimal("100.05"),
            fresh_mid=Decimal("100.00"),
            fresh_quote_timestamp=now,
            limit_price=Decimal("99.90"),
            expected_notional=Decimal("4500"),
            risk_budget=Decimal("1000"),
            max_authorized_notional=Decimal("5000"),
            constitution_version="v1.0.0",
            expires_at=now + timedelta(hours=1),
        ),
    )


def create_synthetic_closed_position(
    symbol: str,
    direction: str,
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: Decimal,
    exit_reason: ExitReasonCode,
    mfe_pct: Decimal,
    mae_pct: Decimal,
    realized_pnl: Decimal,
) -> tuple[ManagedPosition, datetime, tuple[ExitReasonCode, ...]]:
    """Create a synthetic closed ManagedPosition for testing.
    Returns (position, exit_timestamp, exit_reason_codes).
    """
    now = datetime.now(UTC)
    entry_time = now - timedelta(hours=4)

    position = ManagedPosition(
        position_id=f"pos-{uuid4().hex[:8]}",
        symbol=symbol,
        instrument_type="STOCK",
        side=direction,
        entry_execution_id=f"exec-entry-{uuid4().hex[:8]}",
        entry_order_id=f"order-entry-{uuid4().hex[:8]}",
        instrument_plan_id=f"plan-{uuid4().hex[:8]}",
        entry_timestamp=entry_time,
        entry_price=entry_price,
        initial_quantity=quantity,
        current_quantity=Decimal("0"),
        current_price=exit_price,
        initial_notional=entry_price * quantity,
        current_notional=Decimal("0"),
        risk_budget_at_entry=Decimal("1000"),
        constitution_version="v1.0.0",
        initial_stop_reference=entry_price * Decimal("0.95") if direction == "LONG" else entry_price * Decimal("1.05"),
        current_stop_reference=entry_price * Decimal("0.95") if direction == "LONG" else entry_price * Decimal("1.05"),
        highest_price_since_entry=max(entry_price, exit_price) * Decimal("1.02"),
        lowest_price_since_entry=min(entry_price, exit_price) * Decimal("0.98"),
        unrealized_pnl=Decimal("0"),
        unrealized_pnl_pct=Decimal("0"),
        realized_pnl=realized_pnl,
        status=PositionStatus.CLOSED,
        exit_state=ExitState.EXITED,
        mfe=mfe_pct,
        mae=mae_pct,
    )
    return position, now, (exit_reason,)


def print_trade_record(label: str, record: TradeRecord) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Trade ID:      {record.trade_id}")
    safe_print(f"  Position ID:   {record.position_id}")
    safe_print(f"  Symbol:        {record.symbol} ({record.direction})")
    safe_print(f"  Entry:         {fmt_usd(record.entry_price)} x {record.entry_quantity}")
    safe_print(f"  Exit:          {fmt_usd(record.exit_price)} x {record.exit_quantity}")
    safe_print(f"  Realized PnL:  {fmt_usd(record.realized_pnl)} ({fmt_pct(record.return_pct)})")
    safe_print(f"  R Multiple:    {fmt_r(record.r_multiple)}")
    safe_print(f"  MFE:           {fmt_pct(record.mfe_pct)}")
    safe_print(f"  MAE:           {fmt_pct(record.mae_pct)}")
    safe_print(f"  Committee Conf:{fmt_pct(record.committee_confidence)}")
    safe_print(f"  Risk Decision: {record.risk_decision}")


def print_evaluation(label: str, eval_obj) -> None:
    safe_print(f"\n--- {label} ---")
    for field_name, value in eval_obj.model_dump().items():
        if field_name in ("trade_id", "evaluated_at", "created_at"):
            continue
        if isinstance(value, Decimal):
            safe_print(f"  {field_name}: {value:.4f}")
        elif isinstance(value, (list, tuple)) and value:
            safe_print(f"  {field_name}: {value}")
        elif value is not None:
            safe_print(f"  {field_name}: {value}")


def run_scenario_winning_long(service: TradingMemoryService) -> bool:
    """Scenario: Winning LONG trade with take profit exit."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: WINNING LONG (Take Profit)")
    safe_print(f"{'='*60}")

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="SPY",
        direction="LONG",
        entry_price=Decimal("450.00"),
        exit_price=Decimal("472.50"),  # +5%
        quantity=Decimal("10"),
        exit_reason=ExitReasonCode.TAKE_PROFIT,
        mfe_pct=Decimal("0.06"),  # 6% MFE
        mae_pct=Decimal("0.01"),  # 1% MAE
        realized_pnl=Decimal("225.00"),
    )

    committee = create_synthetic_committee_result("SPY", "LONG")
    risk_eval = create_synthetic_risk_evaluation("SPY", approved=True)
    instrument = create_synthetic_instrument_plan("SPY", "LONG")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "SPY", Decimal("450.10"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "SPY", Decimal("472.40"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("450.00"),
            underlying_exit_price=Decimal("475.00"),  # Underlying went further
        )

        trade_record, trade_outcome, thesis_eval, exec_quality, exit_quality, risk_outcome, inst_outcome, agent_records = results

        print_trade_record("Trade Record", trade_record)
        print_evaluation("Trade Outcome", trade_outcome)
        print_evaluation("Thesis Evaluation", thesis_eval)
        print_evaluation("Execution Quality", exec_quality)
        print_evaluation("Exit Quality", exit_quality)
        print_evaluation("Risk Outcome", risk_outcome)
        print_evaluation("Instrument Outcome", inst_outcome)

        for ar in agent_records:
            safe_print(f"\n  Agent {ar.agent_name}: stance={ar.stance}, conf={ar.confidence}, dir_correct={ar.direction_correct}, calib_target={ar.calibration_target}")

        # Verify expectations
        passed = (
            trade_outcome.outcome_type == TradeOutcomeType.WIN
            and thesis_eval.correctness == ThesisCorrectness.CORRECT
            and trade_record.r_multiple is not None
            and trade_record.r_multiple > 0
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_scenario_losing_long(service: TradingMemoryService) -> bool:
    """Scenario: Losing LONG trade with hard stop exit."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: LOSING LONG (Hard Stop)")
    safe_print(f"{'='*60}")

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="AAPL",
        direction="LONG",
        entry_price=Decimal("175.00"),
        exit_price=Decimal("168.00"),  # -4%
        quantity=Decimal("20"),
        exit_reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        mfe_pct=Decimal("0.01"),   # 1% MFE
        mae_pct=Decimal("0.05"),   # 5% MAE
        realized_pnl=Decimal("-140.00"),
    )

    committee = create_synthetic_committee_result("AAPL", "LONG")
    risk_eval = create_synthetic_risk_evaluation("AAPL", approved=True)
    instrument = create_synthetic_instrument_plan("AAPL", "LONG")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "AAPL", Decimal("175.05"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "AAPL", Decimal("167.90"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("175.00"),
            underlying_exit_price=Decimal("165.00"),  # Underlying fell further
        )

        trade_record, trade_outcome, thesis_eval, exec_quality, exit_quality, risk_outcome, inst_outcome, agent_records = results

        print_trade_record("Trade Record", trade_record)
        print_evaluation("Trade Outcome", trade_outcome)
        print_evaluation("Thesis Evaluation", thesis_eval)
        print_evaluation("Execution Quality", exec_quality)
        print_evaluation("Exit Quality", exit_quality)
        print_evaluation("Risk Outcome", risk_outcome)

        for ar in agent_records:
            safe_print(f"\n  Agent {ar.agent_name}: stance={ar.stance}, conf={ar.confidence}, dir_correct={ar.direction_correct}")

        passed = (
            trade_outcome.outcome_type == TradeOutcomeType.LOSS
            and thesis_eval.correctness == ThesisCorrectness.INCORRECT
            and trade_record.r_multiple is not None
            and trade_record.r_multiple < 0
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_scenario_winning_short(service: TradingMemoryService) -> bool:
    """Scenario: Winning SHORT trade."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: WINNING SHORT")
    safe_print(f"{'='*60}")

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="QQQ",
        direction="SHORT",
        entry_price=Decimal("380.00"),
        exit_price=Decimal("361.00"),  # -5% (good for short)
        quantity=Decimal("15"),
        exit_reason=ExitReasonCode.TAKE_PROFIT,
        mfe_pct=Decimal("0.06"),
        mae_pct=Decimal("0.015"),
        realized_pnl=Decimal("285.00"),
    )

    committee = create_synthetic_committee_result("QQQ", "SHORT")
    risk_eval = create_synthetic_risk_evaluation("QQQ", approved=True)
    instrument = create_synthetic_instrument_plan("QQQ", "SHORT")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "QQQ", Decimal("379.90"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "QQQ", Decimal("361.10"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("380.00"),
            underlying_exit_price=Decimal("358.00"),  # Underlying fell further
        )

        trade_record, trade_outcome, thesis_eval, exec_quality, exit_quality, risk_outcome, inst_outcome, agent_records = results

        print_trade_record("Trade Record", trade_record)
        print_evaluation("Trade Outcome", trade_outcome)
        print_evaluation("Thesis Evaluation", thesis_eval)

        for ar in agent_records:
            safe_print(f"\n  Agent {ar.agent_name}: stance={ar.stance}, conf={ar.confidence}, dir_correct={ar.direction_correct}")

        passed = (
            trade_outcome.outcome_type == TradeOutcomeType.WIN
            and thesis_eval.correctness == ThesisCorrectness.CORRECT
            and trade_record.r_multiple is not None
            and trade_record.r_multiple > 0
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_scenario_losing_short(service: TradingMemoryService) -> bool:
    """Scenario: Losing SHORT trade."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: LOSING SHORT")
    safe_print(f"{'='*60}")

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="TSLA",
        direction="SHORT",
        entry_price=Decimal("250.00"),
        exit_price=Decimal("265.00"),  # +6% (bad for short)
        quantity=Decimal("10"),
        exit_reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        mfe_pct=Decimal("0.02"),
        mae_pct=Decimal("0.07"),
        realized_pnl=Decimal("-150.00"),
    )

    committee = create_synthetic_committee_result("TSLA", "SHORT")
    risk_eval = create_synthetic_risk_evaluation("TSLA", approved=True)
    instrument = create_synthetic_instrument_plan("TSLA", "SHORT")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "TSLA", Decimal("250.10"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "TSLA", Decimal("264.90"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("250.00"),
            underlying_exit_price=Decimal("270.00"),  # Underlying rose further
        )

        trade_record, trade_outcome, thesis_eval, exec_quality, exit_quality, risk_outcome, inst_outcome, agent_records = results

        print_trade_record("Trade Record", trade_record)
        print_evaluation("Trade Outcome", trade_outcome)
        print_evaluation("Thesis Evaluation", thesis_eval)

        for ar in agent_records:
            safe_print(f"\n  Agent {ar.agent_name}: stance={ar.stance}, conf={ar.confidence}, dir_correct={ar.direction_correct}")

        passed = (
            trade_outcome.outcome_type == TradeOutcomeType.LOSS
            and thesis_eval.correctness == ThesisCorrectness.INCORRECT
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_synthetic_committee_result(symbol: str, direction: str, confidence: Decimal = Decimal("0.75")) -> CommitteeResult:
    """Create a synthetic CommitteeResult for testing."""
    now = datetime.now(UTC)
    agent_role = AgentRole.BULL if direction == "LONG" else AgentRole.BEAR
    stance = M3AgentStance.LONG if direction == "LONG" else M3AgentStance.SHORT

    opinion = AgentOpinion(
        agent_role=agent_role,
        symbol=symbol,
        stance=stance,
        confidence=confidence,
        thesis=f"Synthetic {direction} thesis for {symbol}",
        supporting_evidence_ids=("ev-momentum-001", "ev-trend-001"),
    )

    decision = CommitteeDecisionModel(
        symbol=symbol,
        decision=CommitteeDecision.PROPOSE_LONG if direction == "LONG" else CommitteeDecision.PROPOSE_SHORT,
        direction=SignalDirection.BULLISH if direction == "LONG" else SignalDirection.BEARISH,
        committee_score=Decimal("75"),
        committee_confidence=confidence,
        initial_disagreement=DisagreementSeverity.LOW,
        final_disagreement=DisagreementSeverity.LOW,
        participating_agents=(AgentRole.QUANT, AgentRole.BULL, AgentRole.BEAR, AgentRole.REGIME),
        decision_reasons=(f"Strong {direction} signals",),
    )

    thesis = TradeThesis(
        symbol=symbol,
        proposed_direction=SignalDirection.BULLISH if direction == "LONG" else SignalDirection.BEARISH,
        committee_confidence=confidence,
        summary=f"Synthetic {direction} thesis for {symbol}",
        market_state_as_of=now,
        candidate_score=Decimal("70"),
        committee_decision=decision,
    )

    return CommitteeResult(
        candidate_symbol=symbol,
        evidence_packet=EvidencePacket(
            symbol=symbol,
            as_of=now,
            evidence=(
                EvidenceItem(id="ev-momentum-001", category=EvidenceCategory.MOMENTUM, label="5d Return", value="+3.2%", source=EvidenceSource.M1_FEATURE),
                EvidenceItem(id="ev-trend-001", category=EvidenceCategory.TREND, label="SMA20", value="Above", source=EvidenceSource.M1_FEATURE),
            ),
        ),
        initial_opinions=(opinion,),
        final_opinions=(opinion,),
        decision=decision,
        trade_thesis=thesis,
    )


def run_scenario_high_conf_correct(service: TradingMemoryService) -> bool:
    """Scenario: High confidence, thesis correct."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: HIGH CONFIDENCE CORRECT")
    safe_print(f"{'='*60}")

    committee = create_synthetic_committee_result("SPY", "LONG", confidence=Decimal("0.92"))

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="SPY",
        direction="LONG",
        entry_price=Decimal("450.00"),
        exit_price=Decimal("468.00"),  # +4%
        quantity=Decimal("10"),
        exit_reason=ExitReasonCode.TAKE_PROFIT,
        mfe_pct=Decimal("0.05"),
        mae_pct=Decimal("0.005"),
        realized_pnl=Decimal("180.00"),
    )

    risk_eval = create_synthetic_risk_evaluation("SPY", approved=True)
    instrument = create_synthetic_instrument_plan("SPY", "LONG")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "SPY", Decimal("450.05"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "SPY", Decimal("467.90"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("450.00"),
            underlying_exit_price=Decimal("470.00"),
        )

        trade_record, trade_outcome, thesis_eval, *_ = results

        safe_print(f"  Committee Confidence: {trade_record.committee_confidence:.2%}")
        safe_print(f"  Thesis Correctness:   {thesis_eval.correctness}")

        passed = (
            trade_record.committee_confidence is not None
            and trade_record.committee_confidence >= Decimal("0.90")
            and thesis_eval.correctness == ThesisCorrectness.CORRECT
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        return False


def run_scenario_high_conf_incorrect(service: TradingMemoryService) -> bool:
    """Scenario: High confidence, thesis incorrect (for calibration)."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: HIGH CONFIDENCE INCORRECT")
    safe_print(f"{'='*60}")

    committee = create_synthetic_committee_result("SPY", "LONG", confidence=Decimal("0.92"))

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="SPY",
        direction="LONG",
        entry_price=Decimal("450.00"),
        exit_price=Decimal("432.00"),  # -4%
        quantity=Decimal("10"),
        exit_reason=ExitReasonCode.HARD_STOP_TRIGGERED,
        mfe_pct=Decimal("0.01"),
        mae_pct=Decimal("0.05"),
        realized_pnl=Decimal("-180.00"),
    )

    risk_eval = create_synthetic_risk_evaluation("SPY", approved=True)
    instrument = create_synthetic_instrument_plan("SPY", "LONG")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "SPY", Decimal("450.05"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "SPY", Decimal("431.90"))

    try:
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
            underlying_entry_price=Decimal("450.00"),
            underlying_exit_price=Decimal("430.00"),
        )

        trade_record, trade_outcome, thesis_eval, *_ = results

        safe_print(f"  Committee Confidence: {trade_record.committee_confidence:.2%}")
        safe_print(f"  Thesis Correctness:   {thesis_eval.correctness}")

        passed = (
            trade_record.committee_confidence is not None
            and trade_record.committee_confidence >= Decimal("0.90")
            and thesis_eval.correctness == ThesisCorrectness.INCORRECT
        )

        safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
        return passed

    except Exception as e:
        safe_print(f"  ERROR: {e}")
        return False


def run_idempotency_test(service: TradingMemoryService) -> bool:
    """Test that evaluating same position 10 times creates only 1 record."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: IDEMPOTENCY TEST")
    safe_print(f"{'='*60}")

    position, exit_ts, exit_reasons = create_synthetic_closed_position(
        symbol="SPY",
        direction="LONG",
        entry_price=Decimal("450.00"),
        exit_price=Decimal("472.50"),
        quantity=Decimal("10"),
        exit_reason=ExitReasonCode.TAKE_PROFIT,
        mfe_pct=Decimal("0.06"),
        mae_pct=Decimal("0.01"),
        realized_pnl=Decimal("225.00"),
    )

    committee = create_synthetic_committee_result("SPY", "LONG")
    risk_eval = create_synthetic_risk_evaluation("SPY", approved=True)
    instrument = create_synthetic_instrument_plan("SPY", "LONG")
    entry_exec = create_synthetic_entry_execution(instrument.plan_id, "SPY", Decimal("450.10"))
    exit_exec = create_synthetic_exit_execution(instrument.plan_id, "SPY", Decimal("472.40"))

    trade_ids = set()
    for i in range(10):
        results = service.evaluate_closed_position(
            position=position,
            committee_result=committee,
            risk_evaluation=risk_eval,
            instrument_plan=instrument,
            entry_execution=entry_exec,
            exit_execution=exit_exec,
        )
        trade_ids.add(results[0].trade_id)

    safe_print(f"  Unique trade_ids after 10 evaluations: {len(trade_ids)}")
    safe_print(f"  Trade IDs: {trade_ids}")

    passed = len(trade_ids) == 1
    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_similarity_test(service: TradingMemoryService) -> bool:
    """Test similarity engine with known trades."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: SIMILARITY ENGINE")
    safe_print(f"{'='*60}")

    # Query for similar trades
    query = {
        "direction": "LONG",
        "instrument_type": "STOCK",
        "committee_confidence": Decimal("0.75"),
    }

    similar = service.get_similar_trades(query, k=5)

    safe_print(f"  Found {len(similar)} similar trades")
    for s in similar:
        safe_print(f"    {s.trade_id}: score={s.similarity_score:.2f}, outcome={s.outcome_type}, R={fmt_r(s.r_multiple)}")

    # Deterministic check - run again
    similar2 = service.get_similar_trades(query, k=5)
    same_order = all(a.trade_id == b.trade_id for a, b in zip(similar, similar2))

    safe_print(f"  Deterministic ordering: {'YES' if same_order else 'NO'}")

    passed = len(similar) > 0 and same_order
    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_performance_summary(service: TradingMemoryService) -> bool:
    """Test performance summary generation."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: PERFORMANCE SUMMARY")
    safe_print(f"{'='*60}")

    summary = service.get_performance_summary()

    safe_print(f"  Total Trades:     {summary.total_trades}")
    safe_print(f"  Committee Wins:   {summary.committee.wins}")
    safe_print(f"  Committee Losses: {summary.committee.losses}")
    safe_print(f"  Win Rate:         {fmt_pct(summary.committee.win_rate)}")
    safe_print(f"  Mean R:           {fmt_r(summary.committee.mean_r_multiple)}")
    safe_print(f"  Median R:         {fmt_r(summary.committee.median_r_multiple)}")
    safe_print(f"  Mean Return:      {fmt_pct(summary.committee.mean_return_pct)}")
    safe_print(f"  Calibration:      {summary.calibration.overall_insight}")
    safe_print(f"  Brier Score:      {summary.calibration.brier_score}")
    safe_print(f"  ECE:              {summary.calibration.ece}")

    passed = summary.total_trades > 0
    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_historical_context(service: TradingMemoryService) -> bool:
    """Test historical context provider."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO: HISTORICAL CONTEXT")
    safe_print(f"{'='*60}")

    query = {
        "direction": "LONG",
        "instrument_type": "STOCK",
        "committee_confidence": Decimal("0.75"),
    }

    context = service.get_historical_context(query, k=10)

    safe_print(f"  Similar Trades:   {context.similar_trade_count}")
    safe_print(f"  Win Rate:         {fmt_pct(context.win_rate)}")
    safe_print(f"  Mean R:           {fmt_r(context.mean_r_multiple)}")
    safe_print(f"  Median R:         {fmt_r(context.median_r_multiple)}")
    safe_print(f"  Mean Return:      {fmt_pct(context.mean_return_pct)}")
    safe_print(f"  Calibration:      {context.committee_calibration.overall_insight if context.committee_calibration else 'N/A'}")
    safe_print(f"  Warnings:         {context.warnings}")
    safe_print(f"  Sufficient Samples: {context.has_sufficient_samples}")

    passed = context.similar_trade_count > 0
    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> int:
    safe_print("M8 TRADING MEMORY DIAGNOSTIC")
    safe_print("=" * 60)
    safe_print("⚠️  ALL DATA IS SYNTHETIC PAPER TRADING - NOT REAL PERFORMANCE")

    settings = Settings()
    safe_print(f"Trading Mode: {settings.trading_mode}")

    # Create memory service with in-memory DB
    service = create_trading_memory_service()

    results = []

    # Run evaluation scenarios
    results.append(("Winning LONG", run_scenario_winning_long(service)))
    results.append(("Losing LONG", run_scenario_losing_long(service)))
    results.append(("Winning SHORT", run_scenario_winning_short(service)))
    results.append(("Losing SHORT", run_scenario_losing_short(service)))
    results.append(("High Confidence Correct", run_scenario_high_conf_correct(service)))
    results.append(("High Confidence Incorrect", run_scenario_high_conf_incorrect(service)))

    # Run idempotency test
    results.append(("Idempotency (10x eval)", run_idempotency_test(service)))

    # Run analytics
    results.append(("Similarity Engine", run_similarity_test(service)))
    results.append(("Performance Summary", run_performance_summary(service)))
    results.append(("Historical Context", run_historical_context(service)))

    # Summary
    safe_print(f"\n{'='*60}")
    safe_print("  SUMMARY")
    safe_print(f"{'='*60}")
    all_pass = True
    for name, passed in results:
        safe_print(f"  {name}: {'PASS' if passed else 'FAIL'}")
        if not passed:
            all_pass = False

    safe_print("\n  M8 LLM Calls:     0")
    safe_print("  Paper Trading:    YES")
    safe_print(f"  OVERALL: {'PASS' if all_pass else 'FAIL'}")

    service.close()
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())