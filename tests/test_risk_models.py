"""Tests for M4 Risk Models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.risk.models import (
    AccountSnapshot,
    NormalizedPosition,
    PortfolioSnapshot,
    RiskBudget,
    RiskCheckResult,
    RiskDecisionType,
    RiskEvaluation,
    RiskReasonCode,
    RiskRuleType,
    RiskState,
)


class TestRiskDecisionType:
    def test_decision_types(self):
        assert RiskDecisionType.APPROVED == "APPROVED"
        assert RiskDecisionType.REDUCED == "REDUCED"
        assert RiskDecisionType.REJECTED == "REJECTED"


class TestRiskReasonCode:
    def test_hard_gate_codes(self):
        assert RiskReasonCode.M3_NO_TRADE == "M3_NO_TRADE"
        assert RiskReasonCode.INVALID_THESIS == "INVALID_THESIS"
        assert RiskReasonCode.POOR_DATA_QUALITY == "POOR_DATA_QUALITY"
        assert RiskReasonCode.LOW_COMMITTEE_CONFIDENCE == "LOW_COMMITTEE_CONFIDENCE"
        assert RiskReasonCode.INVALID_PRICE == "INVALID_PRICE"
        assert RiskReasonCode.KILL_SWITCH_ACTIVE == "KILL_SWITCH_ACTIVE"
        assert RiskReasonCode.DAILY_LOSS_LIMIT == "DAILY_LOSS_LIMIT"
        assert RiskReasonCode.MAX_DRAWDOWN == "MAX_DRAWDOWN"
        assert RiskReasonCode.CALCULATION_FAILURE == "CALCULATION_FAILURE"

    def test_soft_reduction_codes(self):
        assert RiskReasonCode.VOLATILITY_REDUCTION == "VOLATILITY_REDUCTION"
        assert RiskReasonCode.LIQUIDITY_REDUCTION == "LIQUIDITY_REDUCTION"
        assert RiskReasonCode.CONFIDENCE_REDUCTION == "CONFIDENCE_REDUCTION"
        assert RiskReasonCode.SYMBOL_CONCENTRATION == "SYMBOL_CONCENTRATION"
        assert RiskReasonCode.GROSS_EXPOSURE == "GROSS_EXPOSURE"
        assert RiskReasonCode.NET_EXPOSURE == "NET_EXPOSURE"
        assert RiskReasonCode.MAX_POSITIONS == "MAX_POSITIONS"
        assert RiskReasonCode.GROUP_CONCENTRATION == "GROUP_CONCENTRATION"
        assert RiskReasonCode.CORRELATION_REDUNDANCY == "CORRELATION_REDUNDANCY"

    def test_approved_code(self):
        assert RiskReasonCode.WITHIN_LIMITS == "WITHIN_LIMITS"


class TestRiskCheckResult:
    def test_hard_rejection_properties(self):
        check = RiskCheckResult(
            rule_name="test",
            rule_type=RiskRuleType.HARD_GATE,
            passed=False,
            reason_code=RiskReasonCode.M3_NO_TRADE,
        )
        assert check.is_hard_rejection is True
        assert check.is_soft_reduction is False

    def test_soft_reduction_properties(self):
        check = RiskCheckResult(
            rule_name="test",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=False,
            reason_code=RiskReasonCode.VOLATILITY_REDUCTION,
            reduction_factor=Decimal("0.5"),
        )
        assert check.is_hard_rejection is False
        assert check.is_soft_reduction is True

    def test_passed_check(self):
        check = RiskCheckResult(
            rule_name="test",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )
        assert check.is_hard_rejection is False
        assert check.is_soft_reduction is False


class TestNormalizedPosition:
    def test_long_position(self):
        pos = NormalizedPosition(
            symbol="AAPL",
            qty=Decimal("100"),
            market_value=Decimal("15000"),
            side="long",
        )
        assert pos.notional == Decimal("15000")
        assert pos.signed_notional == Decimal("15000")

    def test_short_position(self):
        pos = NormalizedPosition(
            symbol="AAPL",
            qty=Decimal("100"),
            market_value=Decimal("15000"),
            side="short",
        )
        assert pos.notional == Decimal("15000")
        assert pos.signed_notional == Decimal("-15000")


class TestAccountSnapshot:
    def test_from_string_values(self):
        acc = AccountSnapshot(
            account_id="test",
            status="ACTIVE",
            currency="USD",
            equity="100000",
            buying_power="200000",
            cash="50000",
            portfolio_value="100000",
            as_of=datetime.now(UTC),
        )
        assert acc.equity == Decimal("100000")
        assert acc.buying_power == Decimal("200000")
        assert acc.cash == Decimal("50000")
        assert acc.portfolio_value == Decimal("100000")


class TestPortfolioSnapshot:
    def test_empty_portfolio(self):
        pf = PortfolioSnapshot(account_id="test", positions=(), as_of=datetime.now(UTC))
        assert pf.position_count == 0
        assert pf.gross_exposure == Decimal("0")
        assert pf.net_exposure == Decimal("0")
        assert pf.long_exposure == Decimal("0")
        assert pf.short_exposure == Decimal("0")

    def test_with_positions(self):
        positions = (
            NormalizedPosition(symbol="AAPL", qty=Decimal("100"), market_value=Decimal("15000"), side="long"),
            NormalizedPosition(symbol="MSFT", qty=Decimal("50"), market_value=Decimal("10000"), side="long"),
            NormalizedPosition(symbol="TSLA", qty=Decimal("20"), market_value=Decimal("5000"), side="short"),
        )
        pf = PortfolioSnapshot(account_id="test", positions=positions, as_of=datetime.now(UTC))
        assert pf.position_count == 3
        assert pf.gross_exposure == Decimal("30000")
        assert pf.net_exposure == Decimal("20000")  # 25000 - 5000
        assert pf.long_exposure == Decimal("25000")
        assert pf.short_exposure == Decimal("5000")

    def test_get_position(self):
        positions = (NormalizedPosition(symbol="AAPL", qty=Decimal("100"), market_value=Decimal("15000"), side="long"),)
        pf = PortfolioSnapshot(account_id="test", positions=positions, as_of=datetime.now(UTC))
        pos = pf.get_position("AAPL")
        assert pos is not None
        assert pos.symbol == "AAPL"
        assert pf.get_position("MSFT") is None


class TestRiskState:
    def test_drawdown_calculation(self):
        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("110000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )
        # Drawdown = (110000 - 100000) / 110000 = 9.09%
        assert state.current_drawdown == Decimal("10000") / Decimal("110000")

    def test_daily_return(self):
        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("98000"),
            daily_realized_pnl=Decimal("-1500"),
            daily_unrealized_pnl=Decimal("-500"),
            last_updated=datetime.now(UTC),
        )
        # Daily PnL = -2000, return = -2000/100000 = -2%
        assert state.daily_pnl == Decimal("-2000")
        assert state.daily_return == Decimal("-0.02")

    def test_with_updated_equity(self):
        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )
        new_state = state.with_updated_equity(Decimal("105000"))
        assert new_state.current_equity == Decimal("105000")
        assert new_state.peak_equity == Decimal("105000")  # New peak
        assert new_state.session_start_equity == Decimal("100000")

    def test_peak_not_exceeded(self):
        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("110000"),
            current_equity=Decimal("110000"),
            last_updated=datetime.now(UTC),
        )
        new_state = state.with_updated_equity(Decimal("105000"))
        assert new_state.peak_equity == Decimal("110000")  # Peak unchanged

    def test_kill_switch(self):
        state = RiskState(
            session_start_equity=Decimal("100000"),
            peak_equity=Decimal("100000"),
            current_equity=Decimal("100000"),
            last_updated=datetime.now(UTC),
        )
        new_state = state.with_kill_switch(True, "Manual trigger")
        assert new_state.kill_switch_active is True
        assert new_state.kill_switch_reason == "Manual trigger"


class TestRiskBudget:
    def test_total_reduction(self):
        budget = RiskBudget(
            base_risk_budget=Decimal("1000"),
            confidence_reduction=Decimal("0.8"),
            volatility_reduction=Decimal("0.9"),
            liquidity_reduction=Decimal("1.0"),
            concentration_reduction=Decimal("1.0"),
            exposure_reduction=Decimal("1.0"),
            correlation_reduction=Decimal("1.0"),
            adjusted_risk_budget=Decimal("720"),
            max_position_notional=Decimal("10000"),
            shares=100,
        )
        # 0.8 * 0.9 * 1.0 * 1.0 * 1.0 * 1.0 = 0.72
        assert budget.total_reduction == Decimal("0.72")

    def test_adjusted_le_base_validation(self):
        with pytest.raises(ValueError):
            RiskBudget(
                base_risk_budget=Decimal("1000"),
                adjusted_risk_budget=Decimal("1100"),  # Exceeds base
                max_position_notional=Decimal("10000"),
                shares=100,
            )

    def test_negative_notional_rejected(self):
        with pytest.raises(ValueError):
            RiskBudget(
                base_risk_budget=Decimal("1000"),
                adjusted_risk_budget=Decimal("500"),
                max_position_notional=Decimal("-100"),
                shares=100,
            )


class TestRiskEvaluation:
    def test_decision_properties(self):
        eval_approved = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
        )
        assert eval_approved.is_approved
        assert not eval_approved.is_reduced
        assert not eval_approved.is_rejected

        eval_reduced = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.REDUCED,
            reason_code=RiskReasonCode.VOLATILITY_REDUCTION,
        )
        assert not eval_reduced.is_approved
        assert eval_reduced.is_reduced
        assert not eval_reduced.is_rejected

        eval_rejected = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.REJECTED,
            reason_code=RiskReasonCode.M3_NO_TRADE,
        )
        assert not eval_rejected.is_approved
        assert not eval_rejected.is_reduced
        assert eval_rejected.is_rejected

    def test_hard_rejections_soft_reductions(self):
        checks = (
            RiskCheckResult(rule_name="a", rule_type=RiskRuleType.HARD_GATE, passed=False, reason_code=RiskReasonCode.M3_NO_TRADE),
            RiskCheckResult(rule_name="b", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION),
            RiskCheckResult(rule_name="c", rule_type=RiskRuleType.HARD_GATE, passed=True),
        )
        eval_ = RiskEvaluation(symbol="AAPL", decision=RiskDecisionType.REJECTED, reason_code=RiskReasonCode.M3_NO_TRADE, checks=checks)
        assert len(eval_.hard_rejections) == 1
        assert eval_.hard_rejections[0].reason_code == RiskReasonCode.M3_NO_TRADE
        assert len(eval_.soft_reductions) == 1
        assert eval_.soft_reductions[0].reason_code == RiskReasonCode.VOLATILITY_REDUCTION

    def test_get_primary_reason(self):
        # Hard rejection takes priority
        checks = (
            RiskCheckResult(rule_name="a", rule_type=RiskRuleType.HARD_GATE, passed=False, reason_code=RiskReasonCode.M3_NO_TRADE),
            RiskCheckResult(rule_name="b", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION),
        )
        eval_ = RiskEvaluation(symbol="AAPL", decision=RiskDecisionType.REJECTED, reason_code=RiskReasonCode.M3_NO_TRADE, checks=checks)
        assert eval_.get_primary_reason() == RiskReasonCode.M3_NO_TRADE

        # Soft reduction if no hard rejection
        checks = (
            RiskCheckResult(rule_name="a", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.VOLATILITY_REDUCTION),
            RiskCheckResult(rule_name="b", rule_type=RiskRuleType.SOFT_REDUCTION, passed=False, reason_code=RiskReasonCode.LIQUIDITY_REDUCTION),
        )
        eval_ = RiskEvaluation(symbol="AAPL", decision=RiskDecisionType.REDUCED, reason_code=RiskReasonCode.VOLATILITY_REDUCTION, checks=checks)
        assert eval_.get_primary_reason() == RiskReasonCode.VOLATILITY_REDUCTION

        # No violations
        checks = (RiskCheckResult(rule_name="a", rule_type=RiskRuleType.HARD_GATE, passed=True),)
        eval_ = RiskEvaluation(symbol="AAPL", decision=RiskDecisionType.APPROVED, reason_code=RiskReasonCode.WITHIN_LIMITS, checks=checks)
        assert eval_.get_primary_reason() == RiskReasonCode.WITHIN_LIMITS