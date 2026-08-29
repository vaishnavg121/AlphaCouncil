"""Tests for M5 Option Sizing."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.options.models import (
    OptionContract,
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionType,
)
from app.options.sizing import OptionSizer
from app.risk.models import RiskBudget


class TestOptionSizer:
    @pytest.fixture
    def sizer(self):
        return OptionSizer(max_contracts_per_plan=10)

    @pytest.fixture
    def risk_budget(self):
        return RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("1000"),
            max_position_notional=Decimal("10000"),
            shares=100,
        )

    @pytest.fixture
    def sample_snapshot(self):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("5.00"),
            bid_size=Decimal("50"),
            ask_price=Decimal("5.10"),
            ask_size=Decimal("50"),
        )
        return OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            implied_volatility=Decimal("0.25"),
            data_quality=OptionDataQualityStatus.GOOD,
        )

    def test_calculate_plan_affordable(self, sizer, sample_snapshot, risk_budget):
        # Premium = 5.10 * 100 = 510, risk budget = 1000 => 1 contract max
        plan = sizer.calculate_plan(
            sample_snapshot,
            risk_budget,
            Decimal("80"),
            ("test",),
        )
        assert plan is not None
        assert plan.planned_contracts == 1
        assert plan.total_premium == Decimal("510")
        assert plan.maximum_loss == Decimal("510")
        assert plan.risk_budget_used == Decimal("510")

    def test_calculate_plan_multiple_contracts(self, sizer, risk_budget):
        # Lower premium = more contracts
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("2.00"),
            bid_size=Decimal("50"),
            ask_price=Decimal("2.10"),
            ask_size=Decimal("50"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            implied_volatility=Decimal("0.25"),
            data_quality=OptionDataQualityStatus.GOOD,
        )
        # Premium = 2.10 * 100 = 210, risk budget = 1000 => 4 contracts
        plan = sizer.calculate_plan(
            snap,
            risk_budget,
            Decimal("80"),
            ("test",),
        )
        assert plan is not None
        assert plan.planned_contracts == 4
        assert plan.total_premium == Decimal("840")
        assert plan.maximum_loss == Decimal("840")

    def test_calculate_plan_max_contracts_cap(self, sizer, risk_budget):
        # Very cheap option - should cap at max_contracts_per_plan
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("0.10"),
            bid_size=Decimal("50"),
            ask_price=Decimal("0.11"),
            ask_size=Decimal("50"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            implied_volatility=Decimal("0.25"),
            data_quality=OptionDataQualityStatus.GOOD,
        )
        # Premium = 0.11 * 100 = 11, risk budget = 1000 => 90 contracts, but cap at 10
        plan = sizer.calculate_plan(
            snap,
            risk_budget,
            Decimal("80"),
            ("test",),
        )
        assert plan is not None
        assert plan.planned_contracts == 10  # Capped

    def test_calculate_plan_unaffordable(self, sizer, risk_budget):
        # Premium > risk budget
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("15.00"),
            bid_size=Decimal("50"),
            ask_price=Decimal("15.10"),
            ask_size=Decimal("50"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            implied_volatility=Decimal("0.25"),
            data_quality=OptionDataQualityStatus.GOOD,
        )
        # Premium = 15.10 * 100 = 1510 > 1000 risk budget
        plan = sizer.calculate_plan(
            snap,
            risk_budget,
            Decimal("80"),
            ("test",),
        )
        assert plan is None

    def test_calculate_plan_zero_risk_budget(self, sizer, sample_snapshot):
        risk_budget = RiskBudget(
            base_risk_budget=Decimal("0"),
            adjusted_risk_budget=Decimal("0"),
            max_position_notional=Decimal("0"),
            shares=0,
        )
        plan = sizer.calculate_plan(
            sample_snapshot,
            risk_budget,
            Decimal("80"),
            ("test",),
        )
        assert plan is None

    def test_max_loss_invariant(self, sizer, risk_budget):
        """Verify maximum_loss <= risk_budget for all plans."""
        for ask in [Decimal("1.00"), Decimal("2.50"), Decimal("5.00"), Decimal("9.90")]:
            contract = OptionContract(
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("150"),
                multiplier=100,
            )
            quote = OptionQuote(
                symbol="AAPL240119C00150000",
                timestamp=datetime.now(),
                bid_price=ask - Decimal("0.10"),
                bid_size=Decimal("50"),
                ask_price=ask,
                ask_size=Decimal("50"),
            )
            snap = OptionMarketSnapshot(
                contract=contract,
                timestamp=datetime.now(),
                quote=quote,
                implied_volatility=Decimal("0.25"),
                data_quality=OptionDataQualityStatus.GOOD,
            )
            plan = sizer.calculate_plan(snap, risk_budget, Decimal("80"), ("test",))
            if plan:
                assert plan.maximum_loss <= risk_budget.adjusted_risk_budget + Decimal("0.01")
                assert plan.risk_budget_used == plan.maximum_loss