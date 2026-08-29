"""Tests for M5 Option Filters."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.options.filters import OptionFilterConfig, OptionFilters, apply_option_filters
from app.options.models import (
    OptionContract,
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionType,
)
from app.risk.models import RiskBudget


class TestOptionFilterConfig:
    def test_defaults(self):
        config = OptionFilterConfig()
        assert config.min_dte == 7
        assert config.target_dte_min == 21
        assert config.target_dte_max == 60
        assert config.max_dte == 90
        assert config.max_spread_pct == Decimal("0.10")


class TestOptionFilters:
    @pytest.fixture
    def filters(self):
        return OptionFilters()

    @pytest.fixture
    def sample_contracts(self):
        today = date.today()
        return [
            OptionContract(
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(today.year, today.month + 1, 19),
                strike_price=Decimal("150"),
                multiplier=100,
            ),
            OptionContract(
                symbol="AAPL240216C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(today.year, today.month + 2, 16),
                strike_price=Decimal("150"),
                multiplier=100,
            ),
            OptionContract(
                symbol="AAPL240621C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(today.year + 1, 6, 21),
                strike_price=Decimal("150"),
                multiplier=100,
            ),
            OptionContract(
                symbol="AAPL230119C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2023, 1, 19),
                strike_price=Decimal("150"),
                multiplier=100,
            ),
        ]

    def test_filter_by_expiry(self, filters, sample_contracts):
        eligible, rejected = filters.filter_by_expiry(sample_contracts)
        # 2 contracts within range (1 month and 2 months out), 2 rejected (expired and 1 year out)
        assert rejected == 2
        assert len(eligible) == 2

    def test_filter_by_moneyness(self, filters):
        contracts = [
            OptionContract(
                symbol="AAPL240119C00100000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("100"),
            ),
            OptionContract(
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("150"),
            ),
            OptionContract(
                symbol="AAPL240119C00200000",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("200"),
            ),
        ]
        underlying_price = Decimal("150")
        eligible, rejected = filters.filter_by_moneyness(contracts, underlying_price)
        # $150 strike is ATM (moneyness = 1.0), within 0.85-1.15 range
        # $100 strike is ITM (moneyness = 1.5), outside range
        # $200 strike is OTM (moneyness = 0.75), outside range
        assert rejected == 2
        assert len(eligible) == 1
        assert eligible[0].strike_price == Decimal("150")

    def test_filter_by_moneyness_put(self, filters):
        contracts = [
            OptionContract(
                symbol="AAPL240119P00100000",
                underlying_symbol="AAPL",
                option_type=OptionType.PUT,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("100"),
            ),
            OptionContract(
                symbol="AAPL240119P00150000",
                underlying_symbol="AAPL",
                option_type=OptionType.PUT,
                expiration_date=date(2024, 1, 19),
                strike_price=Decimal("150"),
            ),
        ]
        underlying_price = Decimal("150")
        eligible, rejected = filters.filter_by_moneyness(contracts, underlying_price)
        # For PUT: moneyness = strike/spot
        # $150 put: moneyness = 1.0 (ATM) - eligible
        # $100 put: moneyness = 0.667 - rejected
        assert rejected == 1
        assert len(eligible) == 1
        assert eligible[0].strike_price == Decimal("150")


class TestApplyOptionFilters:
    @pytest.fixture
    def risk_budget(self):
        return RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("1000"),
            max_position_notional=Decimal("10000"),
            shares=100,
        )

    @pytest.fixture
    def sample_snapshots(self):
        today = date.today()
        exp_date = date(today.year, today.month + 1, 19)

        def make_snap(symbol, strike, bid, ask):
            contract = OptionContract(
                symbol=symbol,
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=exp_date,
                strike_price=strike,
                multiplier=100,
            )
            quote = OptionQuote(
                symbol=symbol,
                timestamp=datetime.now(),
                bid_price=bid,
                bid_size=Decimal("10"),
                ask_price=ask,
                ask_size=Decimal("15"),
            )
            return OptionMarketSnapshot(
                contract=contract,
                timestamp=datetime.now(),
                quote=quote,
                implied_volatility=Decimal("0.25"),
                data_quality=OptionDataQualityStatus.GOOD,
            )

        return {
            "AAPL240119C00150000": make_snap("AAPL240119C00150000", Decimal("150"), Decimal("5.00"), Decimal("5.10")),
            "AAPL240119C00155000": make_snap("AAPL240119C00155000", Decimal("155"), Decimal("3.00"), Decimal("3.10")),
            "AAPL240119C00160000": make_snap("AAPL240119C00160000", Decimal("160"), Decimal("1.50"), Decimal("1.70")),
            "AAPL240119C00200000": make_snap("AAPL240119C00200000", Decimal("200"), Decimal("0.10"), Decimal("0.50")),  # Wide spread
        }

    def test_full_filter_pipeline(self, sample_snapshots, risk_budget):
        chain = list(sample_snapshots.values())
        chain = [s.contract for s in chain]

        eligible, stats = apply_option_filters(
            chain,
            sample_snapshots,
            Decimal("150"),
            risk_budget,
        )

        assert stats["total_retrieved"] == 4
        assert stats["eligible"] > 0
        # $200 strike OTM should be rejected by moneyness
        # $160 with wide spread may be rejected
        assert all(s.contract.strike_price <= Decimal("155") for s in eligible)