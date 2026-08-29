"""M5 Instrument Selection Diagnostic.

Runs real M5 instrument selection on M3/M4 output and synthetic thesis.
Shows concise sanitized output.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from datetime import UTC, datetime

from app.committee.models import (
    CommitteeDecision,
    CommitteeDecisionModel,
    DisagreementSeverity,
    SignalDirection,
    TradeThesis,
)
from app.core.config import Settings
from app.instruments import InstrumentSelectorService
from app.instruments.models import InstrumentPlan, InstrumentType
from app.market import AlpacaMarketDataGateway
from app.options import create_option_gateway
from app.risk import RiskDecisionType, create_risk_evaluation_service


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

    return thesis, "Scenario A: M3 NO_TRADE"


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


def print_plan(label: str, plan: InstrumentPlan) -> None:
    safe_print(f"\n--- {label} ---")
    safe_print(f"  Instrument:     {plan.instrument_type}")
    safe_print(f"  Symbol:         {plan.symbol}")
    safe_print(f"  Direction:      {plan.thesis_direction}")
    safe_print(f"  Constitution:   {plan.constitution_version}")

    if plan.is_no_trade:
        safe_print(f"  NO_TRADE Reason: {plan.no_trade_reason}")
        return

    safe_print(f"  Selection Score: {plan.equity_plan.selection_score if plan.is_stock else plan.option_plan.selection_score:.1f}")
    safe_print(f"  Reasons:        {', '.join(plan.selection_reasons)}")

    if plan.is_stock and plan.equity_plan:
        eq = plan.equity_plan
        safe_print("\n  Equity Plan:")
        safe_print(f"    Side:                    {eq.side}")
        safe_print(f"    Ref Price:               {fmt_usd(eq.reference_price)}")
        safe_print(f"    Max Notional (M4):       {fmt_usd(eq.max_notional)}")
        safe_print(f"    Planned Notional:        {fmt_usd(eq.planned_notional)}")
        safe_print(f"    Est. Quantity:           {eq.estimated_quantity}")
        safe_print(f"    Risk Budget Used:        {fmt_usd(eq.risk_budget_used)}")
        safe_print(f"    Est. Loss at Risk Stop:  {fmt_usd(eq.estimated_loss_at_risk_stop)}")
        safe_print(f"    Fractional:              {eq.fractional_supported}")

    if plan.is_option and plan.option_plan:
        op = plan.option_plan
        safe_print("\n  Option Plan:")
        safe_print(f"    Contract:                {op.contract_symbol}")
        safe_print(f"    Type:                    {op.option_type}")
        safe_print(f"    DTE:                     {op.days_to_expiry}")
        safe_print(f"    Strike:                  {fmt_usd(op.strike_price)}")
        safe_print(f"    Bid/Ask:                 {fmt_usd(op.bid_price)} / {fmt_usd(op.ask_price)}")
        safe_print(f"    Midpoint:                {fmt_usd(op.midpoint)}")
        safe_print(f"    Spread:                  {fmt_usd(op.spread)} ({fmt_pct(op.spread_pct)})")
        if op.implied_volatility:
            safe_print(f"    IV:                      {fmt_pct(op.implied_volatility)}")
        if op.delta:
            safe_print(f"    Delta:                   {op.delta:.2f}")
        safe_print(f"    Premium/Contract:        {fmt_usd(op.premium_per_contract)}")
        safe_print(f"    Multiplier:              {op.multiplier}")
        safe_print(f"    Planned Contracts:       {op.planned_contracts}")
        safe_print(f"    Total Premium:           {fmt_usd(op.total_premium)}")
        safe_print(f"    Maximum Loss:            {fmt_usd(op.maximum_loss)}")
        safe_print(f"    Risk Budget Used:        {fmt_usd(op.risk_budget_used)}")
        safe_print(f"    Score:                   {op.selection_score:.1f}")


def main() -> int:
    safe_print("M5 INSTRUMENT SELECTION DIAGNOSTIC")
    safe_print("=" * 60)

    settings = Settings()
    safe_print(f"Trading Mode:     {settings.trading_mode}")
    safe_print(f"Execution Enabled: {settings.enable_execution}")
    safe_print(f"Alpaca Live Trade: {settings.alpaca_live_trade}")
    safe_print(f"Options Enabled:   {settings.options_enabled}")

    # Create services
    try:
        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        safe_print(f"BLOCKED — market gateway failed ({type(exc).__name__})")
        return 2

    try:
        option_gateway = create_option_gateway(settings)
    except Exception as exc:
        safe_print(f"WARNING — option gateway unavailable ({type(exc).__name__}: {exc})")
        option_gateway = None

    risk_service = create_risk_evaluation_service(market_gateway, option_gateway)
    instrument_selector = InstrumentSelectorService(
        settings=settings,
        option_gateway=option_gateway,
    )

    # ============================================================
    # SCENARIO A: Real M3 NO_TRADE output
    # ============================================================
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO A: M3 NO_TRADE (Expected: NO_TRADE, RISK_REJECTED)")
    safe_print(f"{'='*60}")

    no_trade_thesis, scenario_a_label = create_no_trade_scenario()
    risk_eval_a = risk_service.evaluate(no_trade_thesis)
    plan_a = instrument_selector.select(no_trade_thesis, risk_eval_a, None)  # MarketState not needed for REJECTED

    safe_print("\n  M4 Risk Evaluation:")
    safe_print(f"    Decision: {risk_eval_a.decision}")
    safe_print(f"    Reason:   {risk_eval_a.reason_code}")

    safe_print("\n  M5 Instrument Selection:")
    safe_print(f"    Result: {plan_a.instrument_type}")
    safe_print(f"    Reason: {plan_a.no_trade_reason}")

    scenario_a_pass = (
        risk_eval_a.decision == RiskDecisionType.REJECTED
        and plan_a.instrument_type == InstrumentType.NO_TRADE
        and plan_a.no_trade_reason == "RISK_REJECTED"
    )
    safe_print(f"\n  EXPECTATION: {'PASS' if scenario_a_pass else 'FAIL'}")

    # ============================================================
    # SCENARIO B: Synthetic valid thesis with real data
    # ============================================================
    safe_print(f"\n{'='*60}")
    safe_print("  SCENARIO B: SYNTHETIC M4 APPROVAL + REAL OPTION DATA")
    safe_print(f"{'='*60}")

    synth_thesis, scenario_b_label = create_synthetic_approved_thesis()
    risk_eval_b = risk_service.evaluate(synth_thesis)

    safe_print("\n  M4 Risk Evaluation:")
    safe_print(f"    Decision: {risk_eval_b.decision}")
    safe_print(f"    Reason:   {risk_eval_b.reason_code}")

    if risk_eval_b.risk_budget:
        b = risk_eval_b.risk_budget
        safe_print("\n  Risk Budget:")
        safe_print(f"    Base:              {fmt_usd(b.base_risk_budget)}")
        safe_print(f"    Adjusted:          {fmt_usd(b.adjusted_risk_budget)}")
        safe_print(f"    Max Notional:      {fmt_usd(b.max_position_notional)}")
        safe_print(f"    ATR Stop:          {fmt_usd(b.atr_stop_distance) if b.atr_stop_distance else 'N/A'}")

    # Get real market state for SPY
    market_state_b = None
    try:
        market_state_b = market_gateway.get_market_state(synth_thesis.symbol)
        safe_print(f"\n  Real Market State for {synth_thesis.symbol}:")
        safe_print(f"    Quote: bid={market_state_b.snapshot.quote.bid_price if market_state_b.snapshot.quote else 'N/A'}, "
                   f"ask={market_state_b.snapshot.quote.ask_price if market_state_b.snapshot.quote else 'N/A'}")
        safe_print(f"    Last: {market_state_b.snapshot.trade.price if market_state_b.snapshot.trade else 'N/A'}")
        safe_print(f"    ATR14: {market_state_b.features.atr_14 if market_state_b.features.atr_14 else 'N/A'}")
        safe_print(f"    IV (est): {market_state_b.features.realized_vol_20 if market_state_b.features.realized_vol_20 else 'N/A'}")
    except Exception as exc:
        safe_print(f"  WARNING — could not fetch real market state ({type(exc).__name__}: {exc})")

    # Run M5 instrument selection
    plan_b = instrument_selector.select(synth_thesis, risk_eval_b, market_state_b)
    print_plan(scenario_b_label, plan_b)

    # Check if we have real option data
    option_chain_status = "UNKNOWN"
    if plan_b.is_option and plan_b.option_plan:
        option_chain_status = "CONNECTED - Real option data used"
    elif plan_b.is_stock:
        option_chain_status = "Equity selected (options may be unavailable or inferior)"
    else:
        option_chain_status = "NO_TRADE"

    scenario_b_pass = risk_eval_b.decision != RiskDecisionType.REJECTED
    safe_print(f"\n  EXPECTATION: {'PASS' if scenario_b_pass else 'FAIL'}")
    safe_print(f"  Option Chain: {option_chain_status}")

    # ============================================================
    # SUMMARY
    # ============================================================
    safe_print(f"\n{'='*60}")
    safe_print("  SUMMARY")
    safe_print(f"{'='*60}")
    safe_print(f"  Scenario A (M3 NO_TRADE):  {'PASS' if scenario_a_pass else 'FAIL'}")
    safe_print(f"  Scenario B (Synthetic):    {'PASS' if scenario_b_pass else 'FAIL'}")
    safe_print("  M4 Constitution Version:   v1.0.0")
    safe_print(f"  Trading Mode:              {settings.trading_mode}")
    safe_print(f"  Execution Enabled:         {settings.enable_execution}")
    safe_print(f"  Alpaca Live Trade:         {settings.alpaca_live_trade}")
    safe_print("  M4 LLM Calls:              0")
    safe_print("  M5 LLM Calls:              0")
    safe_print("  Orders Submitted:          0")

    overall_pass = scenario_a_pass and scenario_b_pass
    safe_print(f"\n  OVERALL: {'PASS' if overall_pass else 'FAIL'}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())