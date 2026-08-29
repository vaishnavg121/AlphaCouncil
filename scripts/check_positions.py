#!/usr/bin/env python
"""M7 Position Monitoring + Exit Management Diagnostic.

Runs real M7 position monitoring and exit management on M3/M4/M5/M6 output
and synthetic positions. Shows concise sanitized output.

Default: DRY RUN - ZERO mutations
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.alpaca.gateway import AlpacaGateway
from app.core.config import Settings
from app.market import AlpacaMarketDataGateway
from app.positions import (
    ExitDecisionType,
    ExitReasonCode,
    ExitState,
    ManagedPosition,
    PositionSnapshot,
    PositionStatus,
    create_exit_management_service,
    create_exit_planner,
    create_position_monitor_service,
    create_position_reconciler,
    create_position_store,
)
from app.risk import RiskState


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


def create_synthetic_long_position() -> ManagedPosition:
    """Create a synthetic long position for testing."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    now = datetime.now(UTC)
    entry_time = now - timedelta(hours=2)

    return ManagedPosition(
        position_id=f"pos-{uuid4().hex[:8]}",
        symbol="SPY",
        instrument_type="STOCK",
        side="LONG",
        entry_execution_id="exec-synthetic-001",
        entry_order_id="order-synthetic-001",
        instrument_plan_id="plan-synthetic-001",
        entry_timestamp=entry_time,
        entry_price=Decimal("450.00"),
        initial_quantity=Decimal("10"),
        current_quantity=Decimal("10"),
        current_price=Decimal("455.00"),
        initial_notional=Decimal("4500.00"),
        current_notional=Decimal("4550.00"),
        risk_budget_at_entry=Decimal("1000.00"),
        constitution_version="v1.0.0",
        initial_stop_reference=Decimal("440.00"),
        current_stop_reference=Decimal("440.00"),
        highest_price_since_entry=Decimal("457.00"),
        lowest_price_since_entry=Decimal("448.00"),
        unrealized_pnl=Decimal("50.00"),
        unrealized_pnl_pct=Decimal("0.0111"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        exit_state=ExitState.NONE,
        mfe=Decimal("0.0155"),
        mae=Decimal("0.0044"),
    )


def create_synthetic_short_position() -> ManagedPosition:
    """Create a synthetic short position for testing."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    now = datetime.now(UTC)
    entry_time = now - timedelta(hours=5)

    return ManagedPosition(
        position_id=f"pos-{uuid4().hex[:8]}",
        symbol="QQQ",
        instrument_type="STOCK",
        side="SHORT",
        entry_execution_id="exec-synthetic-002",
        entry_order_id="order-synthetic-002",
        instrument_plan_id="plan-synthetic-002",
        entry_timestamp=entry_time,
        entry_price=Decimal("380.00"),
        initial_quantity=Decimal("5"),
        current_quantity=Decimal("5"),
        current_price=Decimal("385.00"),
        initial_notional=Decimal("1900.00"),
        current_notional=Decimal("1925.00"),
        risk_budget_at_entry=Decimal("500.00"),
        constitution_version="v1.0.0",
        initial_stop_reference=Decimal("395.00"),
        current_stop_reference=Decimal("395.00"),
        highest_price_since_entry=Decimal("387.00"),
        lowest_price_since_entry=Decimal("378.00"),
        unrealized_pnl=Decimal("-25.00"),
        unrealized_pnl_pct=Decimal("-0.0131"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        exit_state=ExitState.NONE,
        mfe=Decimal("0.0052"),
        mae=Decimal("0.0184"),
    )


def create_synthetic_stop_breached_long() -> ManagedPosition:
    """Create a synthetic long position with stop breached."""
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    now = datetime.now(UTC)
    entry_time = now - timedelta(hours=24)

    return ManagedPosition(
        position_id=f"pos-{uuid4().hex[:8]}",
        symbol="AAPL",
        instrument_type="STOCK",
        side="LONG",
        entry_execution_id="exec-synthetic-003",
        entry_order_id="order-synthetic-003",
        instrument_plan_id="plan-synthetic-003",
        entry_timestamp=entry_time,
        entry_price=Decimal("175.00"),
        initial_quantity=Decimal("20"),
        current_quantity=Decimal("20"),
        current_price=Decimal("168.00"),
        initial_notional=Decimal("3500.00"),
        current_notional=Decimal("3360.00"),
        risk_budget_at_entry=Decimal("1000.00"),
        constitution_version="v1.0.0",
        initial_stop_reference=Decimal("170.00"),
        current_stop_reference=Decimal("170.00"),
        highest_price_since_entry=Decimal("178.00"),
        lowest_price_since_entry=Decimal("168.00"),
        unrealized_pnl=Decimal("-140.00"),
        unrealized_pnl_pct=Decimal("-0.04"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        exit_state=ExitState.NONE,
        mfe=Decimal("0.0171"),
        mae=Decimal("0.04"),
    )


def create_synthetic_kill_switch_active(risk_state: RiskState) -> RiskState:
    """Create risk state with kill switch active."""
    return risk_state.with_kill_switch(True, "Manual trigger for testing")


def print_position(label: str, position: ManagedPosition) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Position ID:   {position.position_id}")
    safe_print(f"  Symbol:        {position.symbol}")
    safe_print(f"  Type:          {position.instrument_type}")
    safe_print(f"  Side:          {position.side}")
    safe_print(f"  Status:        {position.status}")
    safe_print(f"  Entry Time:    {position.entry_timestamp}")
    safe_print(f"  Entry Price:   {fmt_usd(position.entry_price)}")
    safe_print(f"  Init Qty:      {position.initial_quantity}")
    safe_print(f"  Curr Qty:      {position.current_quantity}")
    safe_print(f"  Curr Price:    {fmt_usd(position.current_price)}")
    safe_print(f"  Init Notional: {fmt_usd(position.initial_notional)}")
    safe_print(f"  Curr Notional: {fmt_usd(position.current_notional)}")
    safe_print(f"  Unrealized PnL:{fmt_usd(position.unrealized_pnl)} ({fmt_pct(position.unrealized_pnl_pct)})")
    safe_print(f"  Realized PnL:  {fmt_usd(position.realized_pnl)}")
    safe_print(f"  Time in Trade: {position.time_in_trade_seconds // 3600}h {(position.time_in_trade_seconds % 3600) // 60}m")
    safe_print(f"  Stop Ref:      {fmt_usd(position.current_stop_reference) if position.current_stop_reference else 'N/A'}")
    safe_print(f"  High Water:    {fmt_usd(position.highest_price_since_entry) if position.highest_price_since_entry else 'N/A'}")
    safe_print(f"  Low Water:     {fmt_usd(position.lowest_price_since_entry) if position.lowest_price_since_entry else 'N/A'}")
    safe_print(f"  MFE:           {fmt_pct(position.mfe)}")
    safe_print(f"  MAE:           {fmt_pct(position.mae)}")


def print_snapshot(label: str, snapshot: PositionSnapshot) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Position ID:   {snapshot.position_id}")
    safe_print(f"  Symbol:        {snapshot.symbol}")
    safe_print(f"  Side:          {snapshot.side}")
    safe_print(f"  Curr Qty:      {snapshot.current_quantity}")
    safe_print(f"  Curr Price:    {fmt_usd(snapshot.current_price)}")
    safe_print(f"  Bid/Ask:       {fmt_usd(snapshot.bid_price) if snapshot.bid_price else 'N/A'} / {fmt_usd(snapshot.ask_price) if snapshot.ask_price else 'N/A'}")
    safe_print(f"  Midpoint:      {fmt_usd(snapshot.midpoint) if snapshot.midpoint else 'N/A'}")
    safe_print(f"  Market Value:  {fmt_usd(snapshot.market_value)}")
    safe_print(f"  Unrealized PnL:{fmt_usd(snapshot.unrealized_pnl)} ({fmt_pct(snapshot.unrealized_pnl_pct)})")
    safe_print(f"  Time in Trade: {snapshot.time_in_trade_seconds // 3600}h {(snapshot.time_in_trade_seconds % 3600) // 60}m")
    safe_print(f"  Distance Stop: {fmt_pct(snapshot.distance_to_stop_pct) if snapshot.distance_to_stop_pct else 'N/A'}")
    safe_print(f"  MFE:           {fmt_pct(snapshot.mfe)}")
    safe_print(f"  MAE:           {fmt_pct(snapshot.mae)}")
    safe_print(f"  ATR Move:      {fmt_pct(snapshot.atr_movement_pct) if snapshot.atr_movement_pct else 'N/A'}")
    safe_print(f"  Data Quality:  {snapshot.data_quality}")


def print_decision(label: str, decision: ExitDecision) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Position ID:   {decision.position_id}")
    safe_print(f"  Symbol:        {decision.symbol}")
    safe_print(f"  Decision:      {decision.decision}")
    safe_print(f"  Urgency:       {decision.urgency}")
    safe_print(f"  Target Qty:    {decision.target_quantity_to_close}")
    safe_print(f"  Remaining Qty: {decision.quantity_remaining}")
    safe_print(f"  Ref Price:     {fmt_usd(decision.reference_price)}")
    safe_print(f"  Bid/Ask:       {fmt_usd(decision.fresh_bid) if decision.fresh_bid else 'N/A'} / {fmt_usd(decision.fresh_ask) if decision.fresh_ask else 'N/A'}")
    safe_print(f"  Reasons:       {', '.join(str(r) for r in decision.reason_codes) if decision.reason_codes else 'NONE'}")


def print_exit_plan(label: str, plan: ExitPlan) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Exit Plan ID:  {plan.exit_plan_id}")
    safe_print(f"  Position ID:   {plan.position_id}")
    safe_print(f"  Symbol:        {plan.symbol}")
    safe_print(f"  Decision:      {plan.decision}")
    safe_print(f"  Side:          {plan.side}")
    safe_print(f"  Quantity:      {plan.quantity}")
    safe_print(f"  Urgency:       {plan.urgency}")
    safe_print(f"  Ref Price:     {fmt_usd(plan.reference_price)}")
    safe_print(f"  Limit Price:   {fmt_usd(plan.limit_price) if plan.limit_price else 'N/A'}")
    safe_print(f"  Expected Notl: {fmt_usd(plan.expected_notional)}")
    safe_print(f"  Reasons:       {', '.join(str(r) for r in plan.reason_codes) if plan.reason_codes else 'NONE'}")
    safe_print(f"  Expires:       {plan.expires_at}")


def print_execution_result(label: str, result) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Exit Plan ID:  {result.exit_plan_id}")
    safe_print(f"  Position ID:   {result.position_id}")
    safe_print(f"  Exec Status:   {result.execution_status}")
    safe_print(f"  Exec Order ID: {result.execution_order_id}")
    safe_print(f"  Filled Qty:    {result.filled_quantity}")
    safe_print(f"  Fill Avg Price: {fmt_usd(result.filled_avg_price) if result.filled_avg_price else 'N/A'}")
    safe_print(f"  Remaining Qty: {result.remaining_quantity}")
    if result.warnings:
        safe_print("  Warnings:")
        for w in result.warnings:
            safe_print(f"    - {w}")
    if result.reason_codes:
        safe_print(f"  Reason Codes:  {', '.join(result.reason_codes)}")


def run_scenario_a(settings: Settings, market_gateway, alpaca_gateway, risk_state: RiskState) -> bool:
    """Scenario A: Healthy long position -> HOLD."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO A: HEALTHY LONG POSITION (Expected: HOLD)")
    safe_print(f"{'='*60}")

    # Create synthetic position
    position = create_synthetic_long_position()
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position", position)

    # Create monitor
    monitor = create_position_monitor_service(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    # Evaluate
    decisions = monitor.monitor_once(risk_state=risk_state, dry_run=True)
    decision = decisions[0] if decisions else None

    if decision:
        print_decision("Exit Decision", decision)
        passed = (
            decision.decision == ExitDecisionType.HOLD
            and ExitReasonCode.WITHIN_LIMITS not in decision.reason_codes
        )
    else:
        safe_print("  NO DECISION RETURNED")
        passed = False

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_scenario_b(settings: Settings, market_gateway, alpaca_gateway, risk_state: RiskState) -> bool:
    """Scenario B: Stop breached long -> EXIT."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO B: STOP BREACHED LONG (Expected: EXIT / HARD_STOP_TRIGGERED)")
    safe_print(f"{'='*60}")

    position = create_synthetic_stop_breached_long()
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position (Stop Breached)", position)

    monitor = create_position_monitor_service(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    decisions = monitor.monitor_once(risk_state=risk_state, dry_run=True)
    decision = decisions[0] if decisions else None

    if decision:
        print_decision("Exit Decision", decision)
        passed = (
            decision.decision == ExitDecisionType.EXIT
            and ExitReasonCode.HARD_STOP_TRIGGERED in decision.reason_codes
        )
    else:
        safe_print("  NO DECISION RETURNED")
        passed = False

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_scenario_c(settings: Settings, market_gateway, alpaca_gateway) -> bool:
    """Scenario C: Kill switch active -> EXIT."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO C: KILL SWITCH ACTIVE (Expected: EXIT / KILL_SWITCH)")
    safe_print(f"{'='*60}")

    position = create_synthetic_long_position()
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position", position)

    # Create risk state with kill switch
    risk_state = create_synthetic_kill_switch_active(
        RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("97000"),
            daily_realized_pnl=Decimal("0"),
            daily_unrealized_pnl=Decimal("0"),
            kill_switch_active=False,
            last_updated=datetime.now(UTC),
        )
    )

    monitor = create_position_monitor_service(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    decisions = monitor.monitor_once(risk_state=risk_state, dry_run=True)
    decision = decisions[0] if decisions else None

    if decision:
        print_decision("Exit Decision", decision)
        passed = (
            decision.decision == ExitDecisionType.EXIT
            and ExitReasonCode.KILL_SWITCH in decision.reason_codes
        )
    else:
        safe_print("  NO DECISION RETURNED")
        passed = False

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_scenario_d(settings: Settings, market_gateway, alpaca_gateway, risk_state: RiskState) -> bool:
    """Scenario D: Take profit triggered -> EXIT."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO D: TAKE PROFIT TRIGGERED (Expected: EXIT / TAKE_PROFIT)")
    safe_print(f"{'='*60}")

    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    now = datetime.now(UTC)
    entry_time = now - timedelta(hours=2)

    position = ManagedPosition(
        position_id=f"pos-{uuid4().hex[:8]}",
        symbol="SPY",
        instrument_type="STOCK",
        side="LONG",
        entry_execution_id="exec-synthetic-004",
        entry_order_id="order-synthetic-004",
        instrument_plan_id="plan-synthetic-004",
        entry_timestamp=entry_time,
        entry_price=Decimal("450.00"),
        initial_quantity=Decimal("10"),
        current_quantity=Decimal("10"),
        current_price=Decimal("495.00"),  # 10% gain
        initial_notional=Decimal("4500.00"),
        current_notional=Decimal("4950.00"),
        risk_budget_at_entry=Decimal("1000.00"),
        constitution_version="v1.0.0",
        initial_stop_reference=Decimal("440.00"),
        current_stop_reference=Decimal("440.00"),
        highest_price_since_entry=Decimal("495.00"),
        lowest_price_since_entry=Decimal("448.00"),
        unrealized_pnl=Decimal("450.00"),
        unrealized_pnl_pct=Decimal("0.10"),
        realized_pnl=Decimal("0"),
        status=PositionStatus.OPEN,
        exit_state=ExitState.NONE,
        mfe=Decimal("0.10"),
        mae=Decimal("0.0044"),
    )
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position (10% Gain)", position)

    monitor = create_position_monitor_service(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    decisions = monitor.monitor_once(risk_state=risk_state, dry_run=True)
    decision = decisions[0] if decisions else None

    if decision:
        print_decision("Exit Decision", decision)
        passed = (
            decision.decision == ExitDecisionType.EXIT
            and ExitReasonCode.TAKE_PROFIT in decision.reason_codes
        )
    else:
        safe_print("  NO DECISION RETURNED")
        passed = False

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_scenario_e(settings: Settings, market_gateway, alpaca_gateway, risk_state: RiskState) -> bool:
    """Scenario E: Exit planning and dry-run execution."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO E: EXIT PLANNING + DRY RUN (Expected: EXIT Plan Created)")
    safe_print(f"{'='*60}")

    position = create_synthetic_stop_breached_long()
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position", position)

    monitor = create_position_monitor_service(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    decisions = monitor.monitor_once(risk_state=risk_state, dry_run=True)
    decision = decisions[0] if decisions else None

    if not decision or decision.decision != ExitDecisionType.EXIT:
        safe_print("  No exit decision generated")
        return False

    print_decision("Exit Decision", decision)

    # Build exit plan
    exit_planner = create_exit_planner(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    exit_plan = exit_planner.build_exit_plan(decision, position, risk_state)
    print_exit_plan("Exit Plan", exit_plan)

    # Dry-run execution
    exec_service = create_exit_management_service(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    exec_result = exec_service.execute_exit(exit_plan, position, dry_run=True)
    print_execution_result("Exit Execution (DRY RUN)", exec_result)

    passed = (
        exec_result.execution_status == "AUTHORIZED"
        and exec_result.execution_order_id is not None
    )

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def run_scenario_f(settings: Settings, market_gateway, alpaca_gateway, risk_state: RiskState) -> bool:
    """Scenario F: Reconciliation - local qty > provider qty."""
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO F: QUANTITY MISMATCH (Expected: RECONCILIATION_REQUIRED)")
    safe_print(f"{'='*60}")

    position = create_synthetic_long_position()
    position.current_quantity = Decimal("8")  # Local thinks 8
    position_store = create_position_store()
    position_store.upsert(position.to_store_record())

    print_position("Synthetic Position (Local qty=8)", position)

    reconciler = create_position_reconciler(
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
    )

    # Reconcile - will show mismatch since provider has 0 (synthetic)
    results = reconciler.reconcile_all()

    for result in results:
        safe_print("\n--- Reconciliation Result ---")
        safe_print(f"  Position ID:   {result.position_id}")
        safe_print(f"  Symbol:        {result.symbol}")
        safe_print(f"  Local Qty:     {result.local_quantity}")
        safe_print(f"  Provider Qty:  {result.provider_quantity}")
        safe_print(f"  Reconciled:    {result.reconciled}")
        safe_print(f"  Action Req:    {result.action_required}")
        safe_print(f"  Mismatch:      {result.mismatch_detected}")
        safe_print(f"  Missing at Provider: {result.position_missing_at_provider}")
        safe_print(f"  Details:       {', '.join(result.details)}")

    # Should detect mismatch and require action
    if results:
        result = results[0]
        passed = (
            result.mismatch_detected
            and result.action_required
        )
    else:
        passed = False

    safe_print(f"\n  EXPECTATION: {'PASS' if passed else 'FAIL'}")
    return passed


def main() -> int:
    safe_print("M7 POSITION MONITORING + EXIT MANAGEMENT DIAGNOSTIC")
    safe_print("=" * 60)

    settings = Settings()
    safe_print(f"Trading Mode:           {settings.trading_mode}")
    safe_print(f"Enable Execution:       {settings.enable_execution}")
    safe_print(f"Enable Paper Execution: {settings.enable_paper_execution}")
    safe_print(f"Alpaca Live Trade:      {settings.alpaca_live_trade}")

    # Create gateways
    try:
        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        safe_print(f"BLOCKED — market gateway failed ({type(exc).__name__}: {exc})")
        return 2

    try:
        alpaca_gateway = AlpacaGateway.from_settings(settings)
    except Exception as exc:
        safe_print(f"WARNING — Alpaca gateway failed ({type(exc).__name__}: {exc})")
        alpaca_gateway = None

    # Create risk state
    risk_state = RiskState(
        session_start_equity=Decimal("100000"),
        peak_equity=Decimal("100000"),
        current_equity=Decimal("100500"),
        daily_realized_pnl=Decimal("0"),
        daily_unrealized_pnl=Decimal("500"),
        kill_switch_active=False,
        last_updated=datetime.now(UTC),
    )

    # Run scenarios
    results = []
    results.append(("Scenario A (Healthy HOLD)", run_scenario_a(settings, market_gateway, alpaca_gateway, risk_state)))
    results.append(("Scenario B (Hard Stop EXIT)", run_scenario_b(settings, market_gateway, alpaca_gateway, risk_state)))
    results.append(("Scenario C (Kill Switch EXIT)", run_scenario_c(settings, market_gateway, alpaca_gateway)))
    results.append(("Scenario D (Take Profit EXIT)", run_scenario_d(settings, market_gateway, alpaca_gateway, risk_state)))
    results.append(("Scenario E (Exit Plan + Dry Run)", run_scenario_e(settings, market_gateway, alpaca_gateway, risk_state)))
    results.append(("Scenario F (Qty Mismatch)", run_scenario_f(settings, market_gateway, alpaca_gateway, risk_state)))

    # Summary
    safe_print(f"\n{'='*60}")
    safe_print("  SUMMARY")
    safe_print(f"{'='*60}")
    all_pass = True
    for name, passed in results:
        safe_print(f"  {name}: {'PASS' if passed else 'FAIL'}")
        if not passed:
            all_pass = False

    safe_print(f"\n  Trading Mode:           {settings.trading_mode}")
    safe_print(f"  Enable Execution:       {settings.enable_execution}")
    safe_print(f"  Enable Paper Execution: {settings.enable_paper_execution}")
    safe_print(f"  Alpaca Live Trade:      {settings.alpaca_live_trade}")
    safe_print("  M7 LLM Calls:           0")
    safe_print("  Orders Submitted:       0 (DRY RUN)")

    safe_print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    from datetime import UTC, datetime
    raise SystemExit(main())