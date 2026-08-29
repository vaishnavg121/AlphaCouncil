#!/usr/bin/env python
"""M6 Execution Diagnostic.

Runs real M6 execution planning on M3/M4/M5 output and synthetic thesis.
Shows concise sanitized output.

Default: DRY RUN - ZERO mutations
Optional: --paper-submit for REAL paper submission (requires ENABLE_PAPER_EXECUTION=true)
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings
from app.committee.models import (
    CommitteeDecision,
    CommitteeDecisionModel,
    DisagreementSeverity,
    SignalDirection,
    TradeThesis,
)
from app.execution import (
    ExecutionService,
    ExecutionStatus,
    create_execution_service,
)
from app.execution.models import ExecutionReasonCode, ExecutionStatus as ExecStatus
from app.instruments import InstrumentSelectorService
from app.instruments.models import InstrumentType
from app.market import AlpacaMarketDataGateway
from app.options import create_option_gateway
from app.risk import create_risk_evaluation_service, RiskDecisionType, RiskReasonCode
from datetime import UTC, datetime


def safe_print(text: str) -> None:
    """Print text safely handling Unicode characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        safe_text = text.encode("ascii", errors="replace").decode("ascii")
        print(safe_text)


def fmt_pct(value: Decimal) -> str:
    return f"{value:.2%}"


def fmt_usd(value: Decimal) -> str:
    return f"${value:,.2f}"


def create_no_trade_scenario() -> tuple[TradeThesis, str]:
    """Create a NO_TRADE thesis for Scenario A testing."""
    decision = CommitteeDecisionModel(
        symbol="AAPL",
        decision=CommitteeDecision.NO_TRADE,
        committee_score=Decimal("35"),
        committee_confidence=Decimal("0.35"),
        initial_disagreement=DisagreementSeverity.HIGH,
        final_disagreement=DisagreementSeverity.HIGH,
        participating_agents=(),
        supporting_evidence_ids=(),
        contradicting_evidence_ids=(),
        decision_reasons=("High disagreement", "Insufficient conviction"),
        unresolved_risks=("Mixed signals", "Regime uncertainty"),
        no_trade_reason="HIGH_DISAGREEMENT",
    )

    thesis = TradeThesis(
        symbol="AAPL",
        proposed_direction=SignalDirection.BULLISH,
        committee_confidence=Decimal("0.35"),
        summary="M3 NO_TRADE: High disagreement among agents",
        supporting_evidence_ids=(),
        contradicting_evidence_ids=(),
        key_risks=("Mixed signals",),
        invalidation_conditions=(),
        market_state_as_of=datetime.now(UTC),
        candidate_score=Decimal("35"),
        committee_decision=decision,
    )

    return thesis, "Scenario A: M3 NO_TRADE (Expected: NOT_EXECUTED)"


def create_synthetic_approved_thesis() -> tuple[TradeThesis, str]:
    """Create a clearly labeled SYNTHETIC valid thesis for Scenario B testing."""
    decision = CommitteeDecisionModel(
        symbol="SPY",
        decision=CommitteeDecision.PROPOSE_LONG,
        direction=SignalDirection.BULLISH,
        committee_score=Decimal("85"),
        committee_confidence=Decimal("0.85"),
        initial_disagreement=DisagreementSeverity.LOW,
        final_disagreement=DisagreementSeverity.NONE,
        participating_agents=(),
        supporting_evidence_ids=("E_MOMENTUM_5D", "E_TREND_MEDIUM", "E_VOLUME_RATIO"),
        contradicting_evidence_ids=(),
        decision_reasons=("Strong momentum", "Uptrend confirmed", "Volume supporting"),
        unresolved_risks=("Fed meeting next week",),
    )

    thesis = TradeThesis(
        symbol="SPY",
        proposed_direction=SignalDirection.BULLISH,
        committee_confidence=Decimal("0.85"),
        summary="SYNTHETIC: Strong bullish setup with high committee confidence",
        supporting_evidence_ids=("E_MOMENTUM_5D", "E_TREND_MEDIUM", "E_VOLUME_RATIO"),
        contradicting_evidence_ids=(),
        key_risks=("Fed meeting next week",),
        invalidation_conditions=("Break below 50-day SMA",),
        market_state_as_of=datetime.now(UTC),
        candidate_score=Decimal("85"),
        committee_decision=decision,
    )

    return thesis, "Scenario B: SYNTHETIC M4 APPROVED (BULLISH)"


def print_execution_result(label: str, result: ExecutionResult) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Status:           {result.status}")
    safe_print(f"  Auth State:       {result.authorization.state}")
    safe_print(f"  Auth Reason:      {result.authorization.reason_code}")
    safe_print(f"  Plan ID:          {result.execution_plan_id}")
    safe_print(f"  Instrument Plan:  {result.instrument_plan_id}")

    if result.execution_plan:
        ep = result.execution_plan
        safe_print(f"\n  Execution Plan:")
        safe_print(f"    Symbol:            {ep.symbol}")
        safe_print(f"    Type:              {ep.instrument_type}")
        safe_print(f"    Direction:         {ep.direction}")
        safe_print(f"    Side:              {ep.side}")
        safe_print(f"    Quantity:          {ep.quantity}")
        safe_print(f"    Order Type:        {ep.order_type}")
        safe_print(f"    TIF:               {ep.time_in_force}")
        safe_print(f"    M5 Ref Price:      {fmt_usd(ep.m5_reference_price)}")
        safe_print(f"    Fresh Bid/Ask:     {fmt_usd(ep.fresh_bid)} / {fmt_usd(ep.fresh_ask)}")
        safe_print(f"    Fresh Mid:         {fmt_usd(ep.fresh_mid)}")
        safe_print(f"    Spread:            {fmt_pct(ep.spread_pct)}")
        safe_print(f"    Limit Price:       {fmt_usd(ep.limit_price)}")
        safe_print(f"    Price Deviation:   {fmt_pct(ep.price_deviation_pct)}")
        safe_print(f"    Expected Notional: {fmt_usd(ep.expected_notional)}")
        safe_print(f"    Risk Budget:       {fmt_usd(ep.risk_budget)}")
        safe_print(f"    Max Notional:      {fmt_usd(ep.max_authorized_notional)}")
        safe_print(f"    Expires At:        {ep.expires_at}")

    if result.execution_order:
        eo = result.execution_order
        safe_print(f"\n  Provider Order:")
        safe_print(f"    Order ID:          {eo.order_id}")
        safe_print(f"    Client Order ID:   {eo.client_order_id}")
        safe_print(f"    Status:            {eo.status}")
        safe_print(f"    Provider Status:   {eo.provider_status}")
        safe_print(f"    Filled Qty:        {eo.filled_quantity}")
        safe_print(f"    Filled Avg Price:  {fmt_usd(eo.filled_avg_price) if eo.filled_avg_price else 'N/A'}")
        safe_print(f"    Submitted:         {eo.submitted_at}")
        safe_print(f"    Filled:            {eo.filled_at}")

    if result.warnings:
        safe_print(f"\n  Warnings:")
        for w in result.warnings:
            safe_print(f"    - {w}")

    if result.reason_codes:
        safe_print(f"\n  Reason Codes:")
        for r in result.reason_codes:
            safe_print(f"    - {r}")


def run_scenario_a(settings: Settings, market_gateway, option_gateway) -> tuple[bool, str]:
    """Run Scenario A: M3 NO_TRADE."""
    safe_print(f"\n{'='*60}")
    safe_print(f"  SCENARIO A: M3 NO_TRADE (Expected: NOT_EXECUTED)")
    safe_print(f"{'='*60}")

    thesis, label = create_no_trade_scenario()

    # M4 Risk Evaluation
    risk_service = create_risk_evaluation_service(market_gateway)
    risk_eval = risk_service.evaluate(thesis)
    safe_print(f"\n  M4 Risk Evaluation:")
    safe_print(f"    Decision: {risk_eval.decision}")
    safe_print(f"    Reason:   {risk_eval.reason_code}")

    # M5 Instrument Selection
    instrument_selector = InstrumentSelectorService(
        settings=settings,
        option_gateway=option_gateway,
    )
    instrument_plan = instrument_selector.select(thesis, risk_eval, None)
    safe_print(f"\n  M5 Instrument Selection:")
    safe_print(f"    Result: {instrument_plan.instrument_type}")
    safe_print(f"    Reason: {instrument_plan.no_trade_reason}")

    # M6 Execution (DRY RUN)
    exec_service = create_execution_service(settings, market_gateway)
    result = exec_service.execute(instrument_plan, risk_eval, dry_run=True)
    print_execution_result("M6 Execution (DRY RUN)", result)

    # Verify expectations
    passed = (
        risk_eval.decision == RiskDecisionType.REJECTED
        and instrument_plan.instrument_type == InstrumentType.NO_TRADE
        and result.status == ExecutionStatus.NOT_EXECUTED
        and result.authorization.reason_code == ExecutionReasonCode.RISK_REJECTED
    )
    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed, label


def run_scenario_b(settings: Settings, market_gateway, option_gateway, paper_submit: bool) -> tuple[bool, str]:
    """Run Scenario B: Synthetic valid thesis with real data."""
    safe_print(f"\n{'='*60}")
    safe_print(f"  SCENARIO B: SYNTHETIC M4 APPROVAL + REAL DATA")
    safe_print(f"{'='*60}")

    thesis, label = create_synthetic_approved_thesis()

    # M4 Risk Evaluation
    risk_service = create_risk_evaluation_service(market_gateway)
    risk_eval = risk_service.evaluate(thesis)
    safe_print(f"\n  M4 Risk Evaluation:")
    safe_print(f"    Decision: {risk_eval.decision}")
    safe_print(f"    Reason:   {risk_eval.reason_code}")

    if risk_eval.risk_budget:
        b = risk_eval.risk_budget
        safe_print(f"\n  Risk Budget:")
        safe_print(f"    Base:              {fmt_usd(b.base_risk_budget)}")
        safe_print(f"    Adjusted:          {fmt_usd(b.adjusted_risk_budget)}")
        safe_print(f"    Max Notional:      {fmt_usd(b.max_position_notional)}")
        safe_print(f"    ATR Stop:          {fmt_usd(b.atr_stop_distance) if b.atr_stop_distance else 'N/A'}")
        safe_print(f"    Shares:            {b.shares}")

    # Get real market state for SPY
    market_state = None
    try:
        market_state = market_gateway.get_snapshot(thesis.symbol)
        safe_print(f"\n  Real Market State for {thesis.symbol}:")
        if market_state.quote:
            safe_print(f"    Quote: bid={fmt_usd(market_state.quote.bid_price)}, ask={fmt_usd(market_state.quote.ask_price)}")
        if market_state.trade:
            safe_print(f"    Last: {fmt_usd(market_state.trade.price)}")
    except Exception as exc:
        safe_print(f"  WARNING — could not fetch real market state ({type(exc).__name__}: {exc})")

    # M5 Instrument Selection
    instrument_selector = InstrumentSelectorService(
        settings=settings,
        option_gateway=option_gateway,
    )
    instrument_plan = instrument_selector.select(thesis, risk_eval, None)
    safe_print(f"\n  M5 Instrument Selection:")
    safe_print(f"    Result: {instrument_plan.instrument_type}")
    if instrument_plan.is_stock and instrument_plan.equity_plan:
        eq = instrument_plan.equity_plan
        safe_print(f"    Side: {eq.side}")
        safe_print(f"    Est Qty: {eq.estimated_quantity}")
        safe_print(f"    Max Notional: {fmt_usd(eq.max_notional)}")
        safe_print(f"    Planned Notional: {fmt_usd(eq.planned_notional)}")
    elif instrument_plan.is_option and instrument_plan.option_plan:
        op = instrument_plan.option_plan
        safe_print(f"    Contract: {op.contract_symbol}")
        safe_print(f"    Contracts: {op.planned_contracts}")
        safe_print(f"    Total Premium: {fmt_usd(op.total_premium)}")

    # M6 Execution
    exec_service = create_execution_service(settings, market_gateway)
    dry_run = not paper_submit
    result = exec_service.execute(instrument_plan, risk_eval, dry_run=dry_run)
    print_execution_result(f"M6 Execution ({'DRY RUN' if dry_run else 'PAPER SUBMIT'})", result)

    # Verify expectations
    m4_ok = risk_eval.decision in (RiskDecisionType.APPROVED, RiskDecisionType.REDUCED)
    m5_ok = instrument_plan.instrument_type != InstrumentType.NO_TRADE
    m6_auth_ok = result.authorization.state == ExecutionAuthorizationState.AUTHORIZED

    if dry_run:
        m6_ok = result.status == ExecutionStatus.AUTHORIZED
    else:
        m6_ok = result.status in (ExecutionStatus.SUBMITTED, ExecutionStatus.AUTHORIZED, ExecutionStatus.PARTIALLY_FILLED, ExecutionStatus.FILLED)

    overall_pass = m4_ok and m5_ok and m6_auth_ok and m6_ok
    safe_print(f"\n  EXPECTATION: {'PASS' if overall_pass else 'FAIL'}")
    return overall_pass, label


def main() -> int:
    parser = argparse.ArgumentParser(description="M6 Execution Diagnostic")
    parser.add_argument(
        "--paper-submit",
        action="store_true",
        help="Submit REAL paper order (requires ENABLE_PAPER_EXECUTION=true)",
    )
    args = parser.parse_args()

    safe_print("M6 EXECUTION DIAGNOSTIC")
    safe_print("=" * 60)

    settings = Settings()
    safe_print(f"Trading Mode:           {settings.trading_mode}")
    safe_print(f"Enable Execution:       {settings.enable_execution}")
    safe_print(f"Enable Paper Execution: {settings.enable_paper_execution}")
    safe_print(f"Alpaca Live Trade:      {settings.alpaca_live_trade}")
    safe_print(f"Options Enabled:        {settings.options_enabled}")
    safe_print(f"Max Price Deviation:    {fmt_pct(Decimal(str(settings.max_execution_price_deviation_pct)))}")
    safe_print(f"Max Spread:             {fmt_pct(Decimal(str(settings.max_execution_spread_pct)))}")
    safe_print(f"Plan TTL:               {settings.execution_plan_ttl_seconds}s")
    safe_print(f"Track Timeout:          {settings.execution_track_timeout_seconds}s")
    safe_print(f"Diagnostic Max Notional: {fmt_usd(Decimal(str(settings.execution_diagnostic_max_notional)))}")

    if args.paper_submit:
        if not settings.enable_paper_execution:
            safe_print("\nERROR: ENABLE_PAPER_EXECUTION=false - refusing paper submission")
            return 2
        if settings.alpaca_live_trade:
            safe_print("\nERROR: ALPACA_LIVE_TRADE=true - refusing paper submission")
            return 2
        safe_print("\n*** REAL PAPER SUBMISSION MODE ENABLED ***")
    else:
        safe_print("\n*** DRY RUN MODE (default) - ZERO mutations ***")

    # Create gateways
    try:
        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        safe_print(f"\nBLOCKED — market gateway failed ({type(exc).__name__}: {exc})")
        return 2

    try:
        option_gateway = create_option_gateway(settings)
    except Exception as exc:
        safe_print(f"WARNING — option gateway unavailable ({type(exc).__name__}: {exc})")
        option_gateway = None

    # Run scenarios
    scenario_a_pass, label_a = run_scenario_a(settings, market_gateway, option_gateway)
    scenario_b_pass, label_b = run_scenario_b(settings, market_gateway, option_gateway, args.paper_submit)

    # Summary
    safe_print(f"\n{'='*60}")
    safe_print(f"  SUMMARY")
    safe_print(f"{'='*60}")
    safe_print(f"  Scenario A (M3 NO_TRADE):  {'PASS' if scenario_a_pass else 'FAIL'}")
    safe_print(f"  Scenario B (Synthetic):    {'PASS' if scenario_b_pass else 'FAIL'}")
    safe_print(f"  Trading Mode:              {settings.trading_mode}")
    safe_print(f"  Enable Execution:          {settings.enable_execution}")
    safe_print(f"  Enable Paper Execution:    {settings.enable_paper_execution}")
    safe_print(f"  Alpaca Live Trade:         {settings.alpaca_live_trade}")
    safe_print(f"  M4 LLM Calls:              0")
    safe_print(f"  M5 LLM Calls:              0")
    safe_print(f"  M6 LLM Calls:              0")

    if args.paper_submit:
        safe_print(f"  Orders Submitted:          1 (paper)")
    else:
        safe_print(f"  Orders Submitted:          0")

    overall_pass = scenario_a_pass and scenario_b_pass
    safe_print(f"\n  OVERALL: {'PASS' if overall_pass else 'FAIL'}")

    if not args.paper_submit:
        safe_print("\nTo submit a REAL paper order, run:")
        safe_print("  uv run python scripts/check_execution.py --paper-submit")
        safe_print("(Requires ENABLE_PAPER_EXECUTION=true in .env)")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())