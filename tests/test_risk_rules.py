"""Tests for M4 Risk Constitution and Rules."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.risk.constitution import CONSTITUTION
from app.risk.models import RiskContext, RiskReasonCode, RiskRuleType
from app.risk.rules import PositionSizer, RiskDecisionEngine, RiskRulesEngine


class TestRiskConstitution:
    def test_version(self):
        assert CONSTITUTION.VERSION == "v1.0.0"
        assert CONSTITUTION.CREATED_AT == "2026-08-28"

    def test_base_parameters(self):
        assert CONSTITUTION.BASE_RISK_PER_TRADE == Decimal("0.01")
        assert CONSTITUTION.MAX_POSITION_NOTIONAL_PCT == Decimal("0.10")
        assert CONSTITUTION.MAX_GROSS_EXPOSURE_PCT == Decimal("1.00")
        assert CONSTITUTION.MAX_NET_EXPOSURE_PCT == Decimal("0.50")
        assert CONSTITUTION.MAX_OPEN_POSITIONS == 10
        assert CONSTITUTION.MAX_SYMBOL_CONCENTRATION_PCT == Decimal("0.05")
        assert CONSTITUTION.MAX_GROUP_CONCENTRATION_PCT == Decimal("0.20")
        assert CONSTITUTION.MAX_CORRELATION == Decimal("0.70")

    def test_hard_gates_exist(self):
        gate_names = [g.name for g in CONSTITUTION.HARD_GATES]
        assert "m3_no_trade" in gate_names
        assert "invalid_thesis" in gate_names
        assert "poor_data_quality" in gate_names
        assert "low_committee_confidence" in gate_names
        assert "invalid_price" in gate_names
        assert "kill_switch" in gate_names
        assert "daily_loss_limit" in gate_names
        assert "max_drawdown" in gate_names

    def test_soft_reductions_exist(self):
        limit_names = [l.name for l in CONSTITUTION.SOFT_REDUCTIONS]
        assert "volatility_reduction" in limit_names
        assert "liquidity_reduction" in limit_names
        assert "confidence_reduction" in limit_names
        assert "symbol_concentration" in limit_names
        assert "gross_exposure" in limit_names
        assert "net_exposure" in limit_names
        assert "max_positions" in limit_names
        assert "group_concentration" in limit_names
        assert "correlation_redundancy" in limit_names

    def test_hard_gate_thresholds(self):
        conf_gate = CONSTITUTION.get_hard_gate("low_committee_confidence")
        assert conf_gate is not None
        assert conf_gate.threshold == Decimal("0.60")
        assert conf_gate.reason_code == RiskReasonCode.LOW_COMMITTEE_CONFIDENCE

        dd_gate = CONSTITUTION.get_hard_gate("max_drawdown")
        assert dd_gate is not None
        assert dd_gate.threshold == Decimal("0.10")

        loss_gate = CONSTITUTION.get_hard_gate("daily_loss_limit")
        assert loss_gate is not None
        assert loss_gate.threshold == Decimal("0.03")

    def test_soft_limit_thresholds(self):
        vol_limit = CONSTITUTION.get_soft_limit("volatility_reduction")
        assert vol_limit is not None
        assert vol_limit.threshold == Decimal("0.03")
        assert vol_limit.reduction_factor == Decimal("0.5")

        liq_limit = CONSTITUTION.get_soft_limit("liquidity_reduction")
        assert liq_limit is not None
        assert liq_limit.threshold == Decimal("1000000")

    def test_sizing_parameters(self):
        assert CONSTITUTION.ATR_STOP_MULTIPLIER == Decimal("2.0")
        assert CONSTITUTION.MIN_STOP_DISTANCE_PCT == Decimal("0.02")
        assert CONSTITUTION.MAX_STOP_DISTANCE_PCT == Decimal("0.10")
        assert CONSTITUTION.MIN_SHARES == 1


class TestRiskRulesEngine:
    @pytest.fixture
    def engine(self):
        return RiskRulesEngine()

    @pytest.fixture
    def base_context(self):
        """Create a base valid context for testing."""
        from app.committee.models import (
            AgentRole,
            CommitteeDecision,
            CommitteeDecisionModel,
            DisagreementSeverity,
            SignalDirection,
            TradeThesis,
        )

        # Minimal valid thesis
        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.PROPOSE_LONG,
            direction=SignalDirection.BULLISH,
            committee_score=Decimal("80"),
            committee_confidence=Decimal("0.8"),
            initial_disagreement=DisagreementSeverity.LOW,
            final_disagreement=DisagreementSeverity.NONE,
            participating_agents=(AgentRole.QUANT, AgentRole.BULL, AgentRole.BEAR, AgentRole.REGIME),
            supporting_evidence_ids=(),
            contradicting_evidence_ids=(),
            decision_reasons=("Test",),
            unresolved_risks=(),
        )

        thesis = TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.8"),
            summary="Test thesis",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
        )

        from app.risk.models import AccountSnapshot, PortfolioSnapshot, RiskState

        account = AccountSnapshot(
            account_id="test",
            status="ACTIVE",
            currency="USD",
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            cash=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            as_of=datetime.now(UTC),
        )

        portfolio = PortfolioSnapshot(
            account_id="test",
            positions=(),
            as_of=datetime.now(UTC),
        )

        risk_state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )

        return RiskContext(
            trade_thesis=thesis,
            reference_price=Decimal("150"),
            atr_14=Decimal("2.0"),
            realized_vol_20=Decimal("0.02"),
            avg_dollar_volume_20=Decimal("50000000"),
            account=account,
            portfolio=portfolio,
            risk_state=risk_state,
        )

    def test_kill_switch_active_rejected(self, engine, base_context):
        ctx = base_context.risk_state.with_kill_switch(True, "Manual")
        ctx = base_context.model_copy(update={"risk_state": ctx})
        checks = engine.evaluate_all(ctx)
        kill_check = next(c for c in checks if c.rule_name == "kill_switch")
        assert kill_check.passed is False
        assert kill_check.reason_code == RiskReasonCode.KILL_SWITCH_ACTIVE

    def test_kill_switch_inactive_passes(self, engine, base_context):
        checks = engine.evaluate_all(base_context)
        kill_check = next(c for c in checks if c.rule_name == "kill_switch")
        assert kill_check.passed is True

    def test_m3_no_trade_rejected(self, engine, base_context):
        # Create NO_TRADE thesis
        from app.committee.models import (
            CommitteeDecision,
            CommitteeDecisionModel,
            DisagreementSeverity,
            SignalDirection,
            TradeThesis,
        )

        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.NO_TRADE,
            committee_score=Decimal("30"),
            committee_confidence=Decimal("0.3"),
            initial_disagreement=DisagreementSeverity.HIGH,
            final_disagreement=DisagreementSeverity.HIGH,
            participating_agents=(),
            supporting_evidence_ids=(),
            contradicting_evidence_ids=(),
            decision_reasons=(),
            unresolved_risks=(),
            no_trade_reason="LOW_CONVICTION",
        )

        thesis = TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.3"),
            summary="Test",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("30"),
            committee_decision=decision,
        )

        ctx = base_context.model_copy(update={"trade_thesis": thesis})
        checks = engine.evaluate_all(ctx)
        m3_check = next(c for c in checks if c.rule_name == "m3_no_trade")
        assert m3_check.passed is False
        assert m3_check.reason_code == RiskReasonCode.M3_NO_TRADE

    def test_low_committee_confidence_rejected(self, engine, base_context):

        thesis = base_context.trade_thesis.model_copy(update={"committee_confidence": Decimal("0.4")})
        ctx = base_context.model_copy(update={"trade_thesis": thesis})
        checks = engine.evaluate_all(ctx)
        conf_check = next(c for c in checks if c.rule_name == "committee_confidence")
        assert conf_check.passed is False
        assert conf_check.reason_code == RiskReasonCode.LOW_COMMITTEE_CONFIDENCE

    def test_committee_confidence_passes_at_threshold(self, engine, base_context):
        # 0.60 is the threshold
        thesis = base_context.trade_thesis.model_copy(update={"committee_confidence": Decimal("0.60")})
        ctx = base_context.model_copy(update={"trade_thesis": thesis})
        checks = engine.evaluate_all(ctx)
        conf_check = next(c for c in checks if c.rule_name == "committee_confidence")
        assert conf_check.passed is True

    def test_invalid_price_rejected(self, engine, base_context):
        ctx = base_context.model_copy(update={"reference_price": Decimal("0")})
        checks = engine.evaluate_all(ctx)
        price_check = next(c for c in checks if c.rule_name == "price_validation")
        assert price_check.passed is False
        assert price_check.reason_code == RiskReasonCode.INVALID_PRICE

    def test_negative_spread_rejected(self, engine, base_context):
        ctx = base_context.model_copy(update={"bid_price": Decimal("151"), "ask_price": Decimal("150")})
        checks = engine.evaluate_all(ctx)
        price_check = next(c for c in checks if c.rule_name == "price_validation")
        assert price_check.passed is False
        assert price_check.reason_code == RiskReasonCode.INVALID_PRICE

    def test_wide_spread_rejected(self, engine, base_context):
        ctx = base_context.model_copy(update={"bid_price": Decimal("100"), "ask_price": Decimal("110")})
        checks = engine.evaluate_all(ctx)
        price_check = next(c for c in checks if c.rule_name == "price_validation")
        assert price_check.passed is False
        assert price_check.reason_code == RiskReasonCode.INVALID_PRICE

    def test_daily_loss_limit_rejected(self, engine, base_context):
        state = base_context.risk_state.with_updated_equity(
            Decimal("96000"),  # 4% loss
            realized_pnl=Decimal("-4000"),
        )
        ctx = base_context.model_copy(update={"risk_state": state, "account": base_context.account.model_copy(update={"equity": Decimal("96000")})})
        checks = engine.evaluate_all(ctx)
        loss_check = next(c for c in checks if c.rule_name == "daily_loss_limit")
        assert loss_check.passed is False
        assert loss_check.reason_code == RiskReasonCode.DAILY_LOSS_LIMIT

    def test_max_drawdown_rejected(self, engine, base_context):
        from app.risk.models import RiskState

        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("120000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )
        ctx = base_context.model_copy(update={"risk_state": state})
        checks = engine.evaluate_all(ctx)
        dd_check = next(c for c in checks if c.rule_name == "max_drawdown")
        assert dd_check.passed is False
        assert dd_check.reason_code == RiskReasonCode.MAX_DRAWDOWN

    def test_volatility_reduction(self, engine, base_context):
        ctx = base_context.model_copy(update={"realized_vol_20": Decimal("0.05")})  # 5% > 3%
        checks = engine.evaluate_all(ctx)
        vol_check = next(c for c in checks if c.rule_name == "volatility")
        assert vol_check.passed is False
        assert vol_check.reason_code == RiskReasonCode.VOLATILITY_REDUCTION
        assert vol_check.reduction_factor is not None
        assert vol_check.reduction_factor < Decimal("1.0")

    def test_liquidity_reduction(self, engine, base_context):
        ctx = base_context.model_copy(update={"avg_dollar_volume_20": Decimal("500000")})  # $500k < $1M
        checks = engine.evaluate_all(ctx)
        liq_check = next(c for c in checks if c.rule_name == "liquidity")
        assert liq_check.passed is False
        assert liq_check.reason_code == RiskReasonCode.LIQUIDITY_REDUCTION
        assert liq_check.reduction_factor is not None

    def test_confidence_reduction(self, engine, base_context):
        # Confidence 0.75 < 0.80 threshold
        thesis = base_context.trade_thesis.model_copy(update={"committee_confidence": Decimal("0.75")})
        ctx = base_context.model_copy(update={"trade_thesis": thesis})
        checks = engine.evaluate_all(ctx)
        conf_check = next(c for c in checks if c.rule_name == "confidence_reduction")
        assert conf_check.passed is False
        assert conf_check.reason_code == RiskReasonCode.CONFIDENCE_REDUCTION
        assert conf_check.reduction_factor == Decimal("0.75")

    def test_symbol_concentration_reduction(self, engine, base_context):
        from app.risk.models import NormalizedPosition

        pos = NormalizedPosition(
            symbol="AAPL",
            qty=Decimal("100"),
            market_value=Decimal("3000"),  # 3% of 100k equity
            side="long",
        )
        portfolio = base_context.portfolio.model_copy(update={"positions": (pos,)})
        ctx = base_context.model_copy(update={"portfolio": portfolio})
        checks = engine.evaluate_all(ctx)
        conc_check = next(c for c in checks if c.rule_name == "symbol_concentration")
        assert conc_check.passed is False
        assert conc_check.reason_code == RiskReasonCode.SYMBOL_CONCENTRATION

    def test_gross_exposure_reduction(self, engine, base_context):
        from app.risk.models import NormalizedPosition

        # 85% gross exposure
        positions = (
            NormalizedPosition(symbol="AAPL", qty=Decimal("100"), market_value=Decimal("40000"), side="long"),
            NormalizedPosition(symbol="MSFT", qty=Decimal("100"), market_value=Decimal("40000"), side="long"),
            NormalizedPosition(symbol="GOOGL", qty=Decimal("10"), market_value=Decimal("5000"), side="short"),
        )
        portfolio = base_context.portfolio.model_copy(update={"positions": positions})
        ctx = base_context.model_copy(update={"portfolio": portfolio})
        checks = engine.evaluate_all(ctx)
        gross_check = next(c for c in checks if c.rule_name == "gross_exposure")
        assert gross_check.passed is False
        assert gross_check.reason_code == RiskReasonCode.GROSS_EXPOSURE

    def test_net_exposure_reduction(self, engine, base_context):
        from app.risk.models import NormalizedPosition

        # 90% net long exposure
        positions = (
            NormalizedPosition(symbol="AAPL", qty=Decimal("100"), market_value=Decimal("45000"), side="long"),
            NormalizedPosition(symbol="MSFT", qty=Decimal("100"), market_value=Decimal("40000"), side="long"),
        )
        portfolio = base_context.portfolio.model_copy(update={"positions": positions})
        ctx = base_context.model_copy(update={"portfolio": portfolio})
        checks = engine.evaluate_all(ctx)
        net_check = next(c for c in checks if c.rule_name == "net_exposure")
        assert net_check.passed is False
        assert net_check.reason_code == RiskReasonCode.NET_EXPOSURE

    def test_max_positions_reduction(self, engine, base_context):
        from app.risk.models import NormalizedPosition

        # 9 positions
        positions = tuple(
            NormalizedPosition(symbol=f"SYM{i}", qty=Decimal("10"), market_value=Decimal("1000"), side="long")
            for i in range(9)
        )
        portfolio = base_context.portfolio.model_copy(update={"positions": positions})
        ctx = base_context.model_copy(update={"portfolio": portfolio})
        checks = engine.evaluate_all(ctx)
        max_check = next(c for c in checks if c.rule_name == "max_positions")
        assert max_check.passed is False
        assert max_check.reason_code == RiskReasonCode.MAX_POSITIONS

    def test_hard_failure_stops_soft_checks(self, engine, base_context):
        # Kill switch active - should still run all checks but soft checks don't matter
        state = base_context.risk_state.with_kill_switch(True)
        ctx = base_context.model_copy(update={"risk_state": state})
        checks = engine.evaluate_all(ctx)
        # Hard checks still run
        assert any(c.rule_name == "kill_switch" and not c.passed for c in checks)
        assert any(c.rule_name == "m3_no_trade" for c in checks)


class TestPositionSizer:
    @pytest.fixture
    def sizer(self):
        return PositionSizer()

    @pytest.fixture
    def base_context(self):
        from app.committee.models import (
            CommitteeDecision,
            CommitteeDecisionModel,
            DisagreementSeverity,
            SignalDirection,
            TradeThesis,
        )

        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.PROPOSE_LONG,
            direction=SignalDirection.BULLISH,
            committee_score=Decimal("80"),
            committee_confidence=Decimal("0.8"),
            initial_disagreement=DisagreementSeverity.LOW,
            final_disagreement=DisagreementSeverity.NONE,
            participating_agents=(),
            supporting_evidence_ids=(),
            contradicting_evidence_ids=(),
            decision_reasons=("Test",),
            unresolved_risks=(),
        )

        thesis = TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.8"),
            summary="Test thesis",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
        )

        from app.risk.models import AccountSnapshot, PortfolioSnapshot, RiskState

        account = AccountSnapshot(
            account_id="test",
            status="ACTIVE",
            currency="USD",
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            cash=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            as_of=datetime.now(UTC),
        )

        portfolio = PortfolioSnapshot(account_id="test", positions=(), as_of=datetime.now(UTC))
        risk_state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )

        return RiskContext(
            trade_thesis=thesis,
            reference_price=Decimal("150"),
            atr_14=Decimal("2.0"),
            realized_vol_20=Decimal("0.02"),
            avg_dollar_volume_20=Decimal("50000000"),
            account=account,
            portfolio=portfolio,
            risk_state=risk_state,
        )

    def test_base_budget_calculation(self, sizer, base_context):
        checks = ()
        budget = sizer.compute_budget(base_context, checks)
        # Base = 100000 * 0.01 = 1000
        assert budget.base_risk_budget == Decimal("1000")
        assert budget.confidence_reduction == Decimal("1.0")
        assert budget.adjusted_risk_budget == Decimal("1000")

    def test_confidence_reduction_applied(self, sizer, base_context):
        from app.risk.models import RiskCheckResult, RiskReasonCode

        checks = (
            RiskCheckResult(
                rule_name="confidence_reduction",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.CONFIDENCE_REDUCTION,
                reduction_factor=Decimal("0.75"),
            ),
        )
        budget = sizer.compute_budget(base_context, checks)
        assert budget.confidence_reduction == Decimal("0.75")
        assert budget.adjusted_risk_budget == Decimal("750")  # 1000 * 0.75

    def test_multiple_reductions_multiplicative(self, sizer, base_context):
        from app.risk.models import RiskCheckResult, RiskReasonCode

        checks = (
            RiskCheckResult(rule_name="a", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.CONFIDENCE_REDUCTION, reduction_factor=Decimal("0.8")),
            RiskCheckResult(rule_name="b", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION, reduction_factor=Decimal("0.5")),
            RiskCheckResult(rule_name="c", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.LIQUIDITY_REDUCTION, reduction_factor=Decimal("0.5")),
        )
        budget = sizer.compute_budget(base_context, checks)
        # 0.8 * 0.5 * 0.5 = 0.2
        assert budget.adjusted_risk_budget == Decimal("200")

    def test_atr_stop_distance(self, sizer, base_context):
        checks = ()
        budget = sizer.compute_budget(base_context, checks)
        # ATR = 2.0, multiplier = 2.0 => stop = 4.0
        # Clamped to min 2% (3.0) and max 10% (15.0) of price 150
        assert budget.atr_stop_distance is not None
        assert budget.atr_stop_distance == Decimal("4.0")

    def test_atr_stop_clamped_to_min(self, sizer, base_context):
        ctx = base_context.model_copy(update={"atr_14": Decimal("0.5")})  # Very low ATR
        checks = ()
        budget = sizer.compute_budget(ctx, checks)
        # 0.5 * 2.0 = 1.0, but min is 2% of 150 = 3.0
        assert budget.atr_stop_distance == Decimal("3.0")

    def test_atr_stop_clamped_to_max(self, sizer, base_context):
        ctx = base_context.model_copy(update={"atr_14": Decimal("20.0")})  # Very high ATR
        checks = ()
        budget = sizer.compute_budget(ctx, checks)
        # 20 * 2 = 40, but max is 10% of 150 = 15.0
        assert budget.atr_stop_distance == Decimal("15.0")

    def test_position_notional_calculation(self, sizer, base_context):
        checks = ()
        budget = sizer.compute_budget(base_context, checks)
        # Risk budget = 1000, stop distance = 4.0, price = 150
        # stop_pct = 4/150 = 0.0267
        # notional = 1000 / 0.0267 = 37500
        # But capped at max 10% of equity = 10000
        assert budget.max_position_notional == Decimal("10000")
        assert budget.shares > 0

    def test_max_notional_cap(self, sizer, base_context):
        # Low vol, high confidence -> large notional, but capped at 10%
        ctx = base_context.model_copy(update={
            "atr_14": Decimal("1.0"),  # Stop = 2.0, stop_pct = 1.33%
            "realized_vol_20": Decimal("0.01"),
        })
        checks = ()
        budget = sizer.compute_budget(ctx, checks)
        # Budget = 1000, stop_pct = 2/150 = 0.0133
        # notional = 1000 / 0.0133 = 75000
        # Capped at 10000
        assert budget.max_position_notional == Decimal("10000")
        assert budget.shares == 66  # 10000 / 150 = 66

    def test_zero_shares_rejected(self, sizer):
        # Zero equity context
        from app.committee.models import (
            CommitteeDecision,
            CommitteeDecisionModel,
            DisagreementSeverity,
            SignalDirection,
            TradeThesis,
        )
        from app.risk.models import AccountSnapshot, PortfolioSnapshot, RiskState

        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.PROPOSE_LONG,
            direction=SignalDirection.BULLISH,
            committee_score=Decimal("80"),
            committee_confidence=Decimal("0.8"),
            initial_disagreement=DisagreementSeverity.LOW,
            final_disagreement=DisagreementSeverity.NONE,
            participating_agents=(),
            supporting_evidence_ids=(),
            contradicting_evidence_ids=(),
            decision_reasons=("Test",),
            unresolved_risks=(),
        )

        thesis = TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.8"),
            summary="Test",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
        )

        account = AccountSnapshot(
            account_id="test", status="ACTIVE", currency="USD",
            equity=Decimal("0"), buying_power=Decimal("0"), cash=Decimal("0"),
            portfolio_value=Decimal("0"), as_of=datetime.now(UTC),
        )

        portfolio = PortfolioSnapshot(account_id="test", positions=(), as_of=datetime.now(UTC))
        risk_state = RiskState(
            session_start_equity=Decimal("0"), peak_equity=Decimal("0"),
            current_equity=Decimal("0"), last_updated=datetime.now(UTC),
        )

        ctx = RiskContext(
            trade_thesis=thesis,
            reference_price=Decimal("150"),
            account=account,
            portfolio=portfolio,
            risk_state=risk_state,
        )

        checks = ()
        budget = sizer.compute_budget(ctx, checks)
        assert budget.adjusted_risk_budget == Decimal("0")
        assert budget.shares == 0


class TestRiskDecisionEngine:
    @pytest.fixture
    def decider(self):
        return RiskDecisionEngine()

    @pytest.fixture
    def base_context(self):
        from app.committee.models import (
            CommitteeDecision,
            CommitteeDecisionModel,
            DisagreementSeverity,
            SignalDirection,
            TradeThesis,
        )
        from app.risk.models import AccountSnapshot, PortfolioSnapshot, RiskState

        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.PROPOSE_LONG,
            direction=SignalDirection.BULLISH,
            committee_score=Decimal("80"),
            committee_confidence=Decimal("0.8"),
            initial_disagreement=DisagreementSeverity.LOW,
            final_disagreement=DisagreementSeverity.NONE,
            participating_agents=(),
            supporting_evidence_ids=(),
            contradicting_evidence_ids=(),
            decision_reasons=("Test",),
            unresolved_risks=(),
        )

        thesis = TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.8"),
            summary="Test",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
        )

        account = AccountSnapshot(
            account_id="test", status="ACTIVE", currency="USD",
            equity=Decimal("100000"), buying_power=Decimal("200000"), cash=Decimal("100000"),
            portfolio_value=Decimal("100000"), as_of=datetime.now(UTC),
        )

        portfolio = PortfolioSnapshot(account_id="test", positions=(), as_of=datetime.now(UTC))
        risk_state = RiskState(
            session_start_equity=Decimal("100000"), peak_equity=Decimal("100000"),
            current_equity=Decimal("100000"), last_updated=datetime.now(UTC),
        )

        return RiskContext(
            trade_thesis=thesis,
            reference_price=Decimal("150"),
            account=account,
            portfolio=portfolio,
            risk_state=risk_state,
        )

    def test_hard_rejection_decision(self, decider, base_context):
        from app.risk.models import RiskBudget, RiskCheckResult, RiskDecisionType, RiskReasonCode

        checks = (
            RiskCheckResult(rule_name="kill_switch", rule_type=RiskRuleType.HARD_GATE, passed=False, reason_code=RiskReasonCode.KILL_SWITCH_ACTIVE),
        )
        budget = RiskBudget(base_risk_budget=Decimal("1000"), adjusted_risk_budget=Decimal("1000"), max_position_notional=Decimal("10000"), shares=100)

        eval_ = decider.decide(base_context, checks, budget)
        assert eval_.decision == RiskDecisionType.REJECTED
        assert eval_.reason_code == RiskReasonCode.KILL_SWITCH_ACTIVE
        assert eval_.risk_budget is None  # REJECTED => no usable budget

    def test_zero_budget_rejected(self, decider, base_context):
        from app.risk.models import RiskBudget, RiskCheckResult, RiskDecisionType

        checks = (RiskCheckResult(rule_name="test", rule_type=RiskRuleType.HARD_GATE, passed=True),)
        budget = RiskBudget(base_risk_budget=Decimal("0"), adjusted_risk_budget=Decimal("0"), max_position_notional=Decimal("0"), shares=0)

        eval_ = decider.decide(base_context, checks, budget)
        assert eval_.decision == RiskDecisionType.REJECTED
        assert eval_.risk_budget is not None  # Budget included for diagnostics

    def test_soft_reduction_decision(self, decider, base_context):
        from app.risk.models import RiskBudget, RiskCheckResult, RiskDecisionType, RiskReasonCode

        checks = (
            RiskCheckResult(rule_name="volatility", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION, reduction_factor=Decimal("0.5")),
        )
        budget = RiskBudget(base_risk_budget=Decimal("1000"), adjusted_risk_budget=Decimal("500"), max_position_notional=Decimal("10000"), shares=50)

        eval_ = decider.decide(base_context, checks, budget)
        assert eval_.decision == RiskDecisionType.REDUCED
        assert eval_.reason_code == RiskReasonCode.VOLATILITY_REDUCTION

    def test_approved_decision(self, decider, base_context):
        from app.risk.models import RiskBudget, RiskCheckResult, RiskDecisionType, RiskReasonCode

        checks = (RiskCheckResult(rule_name="test", rule_type=RiskRuleType.HARD_GATE, passed=True),)
        budget = RiskBudget(base_risk_budget=Decimal("1000"), adjusted_risk_budget=Decimal("1000"), max_position_notional=Decimal("10000"), shares=100)

        eval_ = decider.decide(base_context, checks, budget)
        assert eval_.decision == RiskDecisionType.APPROVED
        assert eval_.reason_code == RiskReasonCode.WITHIN_LIMITS

    def test_zero_shares_rejected_not_reduced(self, decider, base_context):
        """ZERO-size 'REDUCED' must not be treated as approval."""
        from app.risk.models import RiskBudget, RiskCheckResult, RiskDecisionType, RiskReasonCode

        checks = (
            RiskCheckResult(rule_name="volatility", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION, reduction_factor=Decimal("0.5")),
        )
        budget = RiskBudget(base_risk_budget=Decimal("1000"), adjusted_risk_budget=Decimal("500"), max_position_notional=Decimal("10000"), shares=0)

        eval_ = decider.decide(base_context, checks, budget)
        assert eval_.decision == RiskDecisionType.REJECTED  # Not REDUCED!
        assert eval_.reason_code == RiskReasonCode.CALCULATION_FAILURE