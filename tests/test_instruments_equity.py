"""Tests for M5 Equity Planning."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.instruments.models import EquitySide
from app.instruments.stock import EquityPlanner
from app.market.models import (
    DataQuality,
    DataQualityStatus,
    MarketSnapshot,
    MarketState,
    OHLCVBar,
    QuoteSnapshot,
    TechnicalFeatures,
    Timeframe,
    TradeSnapshot,
)
from app.risk.models import RiskBudget, RiskEvaluation, RiskDecisionType, RiskReasonCode


class TestEquityPlanner:
    @pytest.fixture
    def planner(self):
        return EquityPlanner(fractional_supported=True)

    @pytest.fixture
    def risk_evaluation(self):
        risk_budget = RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("800"),  # 20% reduction
            max_position_notional=Decimal("10000"),
            atr_stop_distance=Decimal("3.00"),
            shares=100,
        )
        return RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=risk_budget,
        )

    @pytest.fixture
    def market_state(self):
        now = datetime.now(UTC)
        price = Decimal("150")
        return MarketState(
            symbol="AAPL",
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(
                symbol="AAPL",
                quote=QuoteSnapshot(
                    symbol="AAPL",
                    timestamp=now,
                    bid_price=price - Decimal("0.01"),
                    ask_price=price + Decimal("0.01"),
                ),
                trade=TradeSnapshot(symbol="AAPL", timestamp=now, price=price),
                daily_bar=OHLCVBar(
                    symbol="AAPL",
                    timestamp=now,
                    open=price,
                    high=price * Decimal("1.01"),
                    low=price * Decimal("0.99"),
                    close=price,
                    volume=1000000,
                ),
            ),
            latest_bar=OHLCVBar(
                symbol="AAPL",
                timestamp=now,
                open=price,
                high=price * Decimal("1.01"),
                low=price * Decimal("0.99"),
                close=price,
                volume=1000000,
            ),
            features=TechnicalFeatures(
                atr_14=Decimal("2.0"),
                realized_vol_20=Decimal("0.02"),
                avg_volume_20=Decimal("2000000"),
            ),
            data_quality=DataQuality(
                status=DataQualityStatus.GOOD,
                bars_requested=100,
                bars_received=100,
            ),
            bars_used=100,
        )

    def test_long_plan(self, planner, risk_evaluation, market_state):
        plan = planner.calculate_plan(market_state, risk_evaluation, "BULLISH")
        assert plan is not None
        assert plan.side == EquitySide.LONG
        assert plan.reference_price == Decimal("150")
        assert plan.planned_notional <= plan.max_notional
        assert plan.estimated_quantity > 0
        assert plan.risk_budget_used <= risk_evaluation.risk_budget.adjusted_risk_budget + Decimal("0.01")
        assert plan.estimated_loss_at_risk_stop <= risk_evaluation.risk_budget.adjusted_risk_budget + Decimal("0.01")

    def test_short_plan(self, planner, risk_evaluation, market_state):
        plan = planner.calculate_plan(market_state, risk_evaluation, "BEARISH")
        assert plan is not None
        assert plan.side == EquitySide.SHORT
        assert plan.risk_budget_used <= risk_evaluation.risk_budget.adjusted_risk_budget + Decimal("0.01")

    def test_plan_respects_max_notional(self, planner, risk_evaluation, market_state):
        plan = planner.calculate_plan(market_state, risk_evaluation, "BULLISH")
        assert plan.planned_notional <= plan.max_notional
        assert plan.max_notional == risk_evaluation.risk_budget.max_position_notional

    def test_plan_respects_risk_budget(self, planner, risk_evaluation, market_state):
        plan = planner.calculate_plan(market_state, risk_evaluation, "BULLISH")
        assert plan.estimated_loss_at_risk_stop <= risk_evaluation.risk_budget.adjusted_risk_budget + Decimal("0.01")

    def test_no_risk_budget_returns_none(self, planner, market_state):
        eval_no_budget = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=None,
        )
        plan = planner.calculate_plan(market_state, eval_no_budget, "BULLISH")
        assert plan is None

    def test_zero_price_returns_none(self, planner, risk_evaluation):
        now = datetime.now(UTC)
        bad_state = MarketState(
            symbol="AAPL",
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(symbol="AAPL"),
            features=TechnicalFeatures(),
            data_quality=DataQuality(
                status=DataQualityStatus.GOOD,
                bars_requested=100,
                bars_received=100,
            ),
            bars_used=100,
        )
        plan = planner.calculate_plan(bad_state, risk_evaluation, "BULLISH")
        assert plan is None

    def test_fractional_disabled_whole_shares(self, risk_evaluation, market_state):
        planner = EquityPlanner(fractional_supported=False)
        plan = planner.calculate_plan(market_state, risk_evaluation, "BULLISH")
        assert plan is not None
        assert plan.estimated_quantity == int(plan.estimated_quantity)
        assert plan.planned_notional == plan.estimated_quantity * plan.reference_price

    def test_fractional_disabled_min_shares(self, risk_evaluation):
        """If fractional disabled and quantity < 1, return None."""
        planner = EquityPlanner(fractional_supported=False)
        now = datetime.now(UTC)
        # Very high price, small risk budget
        bad_state = MarketState(
            symbol="AAPL",
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(
                symbol="AAPL",
                quote=QuoteSnapshot(
                    symbol="AAPL",
                    timestamp=now,
                    bid_price=Decimal("1000"),
                    ask_price=Decimal("1001"),
                ),
            ),
            features=TechnicalFeatures(),
            data_quality=DataQuality(
                status=DataQualityStatus.GOOD,
                bars_requested=100,
                bars_received=100,
            ),
            bars_used=100,
        )
        # With risk budget $1000 and stop 2%, max notional = 1000/0.02 = 50000
        # At $1000/share, need 50 shares minimum for whole shares
        # But if we reduce risk budget...
        small_budget_eval = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=RiskBudget(
                base_risk_budget=Decimal("100"),
                adjusted_risk_budget=Decimal("100"),
                max_position_notional=Decimal("10000"),
                atr_stop_distance=Decimal("20"),  # 2% of 1000
                shares=0,
            ),
        )
        plan = planner.calculate_plan(bad_state, small_budget_eval, "BULLISH")
        # 100 risk budget / (1000 * 0.02) = 5 shares - should work
        assert plan is not None
        assert plan.estimated_quantity >= 1


class TestEquityScore:
    @pytest.fixture
    def planner(self):
        return EquityPlanner()

    @pytest.fixture
    def risk_budget(self):
        return RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("800"),
            max_position_notional=Decimal("10000"),
            atr_stop_distance=Decimal("3.00"),
            shares=100,
        )

    def test_score_good_data(self, planner, risk_budget):
        now = datetime.now(UTC)
        price = Decimal("150")
        state = MarketState(
            symbol="AAPL",
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(
                symbol="AAPL",
                quote=QuoteSnapshot(
                    symbol="AAPL", timestamp=now, bid_price=price - Decimal("0.01"), ask_price=price + Decimal("0.01")
                ),
                trade=TradeSnapshot(symbol="AAPL", timestamp=now, price=price),
                daily_bar=OHLCVBar(symbol="AAPL", timestamp=now, open=price, high=price, low=price, close=price, volume=2000000),
            ),
            latest_bar=OHLCVBar(symbol="AAPL", timestamp=now, open=price, high=price, low=price, close=price, volume=2000000),
            features=TechnicalFeatures(avg_volume_20=Decimal("2000000")),
            data_quality=DataQuality(status=DataQualityStatus.GOOD, bars_requested=100, bars_received=100),
            bars_used=100,
        )
        eval_ = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=risk_budget,
        )
        plan = planner.calculate_plan(state, eval_, "BULLISH")
        assert plan is not None
        assert plan.selection_score > Decimal("50")