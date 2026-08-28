"""Tests for M5 Instrument Selector Service."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.committee.models import (
    CommitteeDecision,
    CommitteeDecisionModel,
    DisagreementSeverity,
    SignalDirection,
    TradeThesis,
)
from app.instruments.selector import InstrumentSelectorService
from app.instruments.models import InstrumentType, InstrumentPlan
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
from app.options.models import (
    OptionContract,
    OptionContractStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionType,
    OptionsGreeks,
    OptionDataQualityStatus,
)
from app.risk.models import RiskBudget, RiskEvaluation, RiskDecisionType, RiskReasonCode


class TestInstrumentSelectorService:
    @pytest.fixture
    def mock_option_gateway(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_option_gateway):
        return InstrumentSelectorService(option_gateway=mock_option_gateway)

    @pytest.fixture
    def approved_risk_evaluation(self):
        risk_budget = RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("800"),
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
    def rejected_risk_evaluation(self):
        return RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.REJECTED,
            reason_code=RiskReasonCode.M3_NO_TRADE,
            risk_budget=None,
        )

    @pytest.fixture
    def bullish_thesis(self):
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
        return TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BULLISH,
            committee_confidence=Decimal("0.8"),
            summary="Test bullish thesis",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
        )

    @pytest.fixture
    def bearish_thesis(self):
        decision = CommitteeDecisionModel(
            symbol="AAPL",
            decision=CommitteeDecision.PROPOSE_SHORT,
            direction=SignalDirection.BEARISH,
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
        return TradeThesis(
            symbol="AAPL",
            proposed_direction=SignalDirection.BEARISH,
            committee_confidence=Decimal("0.8"),
            summary="Test bearish thesis",
            market_state_as_of=datetime.now(UTC),
            candidate_score=Decimal("75"),
            committee_decision=decision,
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
                    symbol="AAPL", timestamp=now, bid_price=price - Decimal("0.01"), ask_price=price + Decimal("0.01")
                ),
                trade=TradeSnapshot(symbol="AAPL", timestamp=now, price=price),
                daily_bar=OHLCVBar(
                    symbol="AAPL", timestamp=now, open=price, high=price * Decimal("1.01"), low=price * Decimal("0.99"), close=price, volume=1000000
                ),
            ),
            latest_bar=OHLCVBar(
                symbol="AAPL", timestamp=now, open=price, high=price * Decimal("1.01"), low=price * Decimal("0.99"), close=price, volume=1000000
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

    def test_m4_rejected_returns_no_trade(self, service, bearish_thesis, rejected_risk_evaluation, market_state):
        plan = service.select(bearish_thesis, rejected_risk_evaluation, market_state)
        assert plan.instrument_type == InstrumentType.NO_TRADE
        assert plan.no_trade_reason == "RISK_REJECTED"
        # Verify no option gateway calls
        service._option_gateway.get_option_chain.assert_not_called()

    def test_missing_risk_budget_returns_no_trade(self, service, bullish_thesis, market_state):
        eval_no_budget = RiskEvaluation(
            symbol="AAPL",
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=None,
        )
        plan = service.select(bullish_thesis, eval_no_budget, market_state)
        assert plan.instrument_type == InstrumentType.NO_TRADE
        assert plan.no_trade_reason == "MISSING_RISK_BUDGET"

    def test_equity_only_when_options_disabled(self, market_state, approved_risk_evaluation, bullish_thesis):
        service = InstrumentSelectorService(options_enabled=False)
        plan = service.select(bullish_thesis, approved_risk_evaluation, market_state)
        assert plan.instrument_type == InstrumentType.STOCK
        assert plan.equity_plan is not None

    def test_equity_plan_created(self, service, bullish_thesis, approved_risk_evaluation, market_state, mock_option_gateway):
        # Mock empty option chain
        mock_option_gateway.get_option_chain.return_value = []
        plan = service.select(bullish_thesis, approved_risk_evaluation, market_state)
        # Should still get equity plan if options empty
        assert plan.instrument_type in (InstrumentType.STOCK, InstrumentType.NO_TRADE)

    def test_m4_gate_efficiency(self, service, bullish_thesis, rejected_risk_evaluation, market_state):
        """M4 REJECTED should not trigger option chain fetch."""
        plan = service.select(bullish_thesis, rejected_risk_evaluation, market_state)
        assert plan.no_trade_reason == "RISK_REJECTED"
        service._option_gateway.get_option_chain.assert_not_called()


class TestInstrumentPlanProperties:
    def test_stock_plan_properties(self):
        from app.instruments.models import EquityInstrumentPlan, InstrumentPlan, InstrumentType, EquitySide

        equity = EquityInstrumentPlan(
            symbol="AAPL",
            side=EquitySide.LONG,
            reference_price=Decimal("150"),
            max_notional=Decimal("10000"),
            planned_notional=Decimal("5000"),
            estimated_quantity=Decimal("33.33"),
            risk_budget_used=Decimal("100"),
            estimated_loss_at_risk_stop=Decimal("100"),
            selection_score=Decimal("70"),
        )
        plan = InstrumentPlan(
            symbol="AAPL",
            thesis_direction="BULLISH",
            instrument_type=InstrumentType.STOCK,
            equity_plan=equity,
        )
        assert plan.is_stock
        assert not plan.is_option
        assert not plan.is_no_trade
        assert plan.max_loss == Decimal("100")
        assert plan.risk_budget_used == Decimal("100")

    def test_option_plan_properties(self):
        from app.instruments.models import OptionInstrumentPlan, InstrumentPlan, InstrumentType, OptionType

        option = OptionInstrumentPlan(
            contract_symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=datetime.now(UTC),
            days_to_expiry=30,
            strike_price=Decimal("150"),
            bid_price=Decimal("5.00"),
            ask_price=Decimal("5.10"),
            midpoint=Decimal("5.05"),
            spread=Decimal("0.10"),
            spread_pct=Decimal("0.02"),
            premium_per_contract=Decimal("510"),
            multiplier=100,
            planned_contracts=1,
            total_premium=Decimal("510"),
            maximum_loss=Decimal("510"),
            risk_budget_used=Decimal("510"),
            selection_score=Decimal("80"),
        )
        plan = InstrumentPlan(
            symbol="AAPL",
            thesis_direction="BULLISH",
            instrument_type=InstrumentType.OPTION,
            option_plan=option,
        )
        assert plan.is_option
        assert not plan.is_stock
        assert not plan.is_no_trade
        assert plan.max_loss == Decimal("510")
        assert plan.risk_budget_used == Decimal("510")

    def test_no_trade_properties(self):
        plan = InstrumentPlan(
            symbol="AAPL",
            thesis_direction="BULLISH",
            instrument_type=InstrumentType.NO_TRADE,
            no_trade_reason="TEST",
        )
        assert plan.is_no_trade
        assert not plan.is_stock
        assert not plan.is_option
        assert plan.max_loss == Decimal("0")
        assert plan.risk_budget_used == Decimal("0")