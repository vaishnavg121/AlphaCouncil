"""Tests for M5 Option Scoring."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.options.filters import OptionFilterConfig
from app.options.models import (
    OptionContract,
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionsGreeks,
    OptionType,
)
from app.options.scoring import OptionScorer, select_best_option
from app.risk.models import RiskBudget


class TestOptionScorer:
    @pytest.fixture
    def scorer(self):
        return OptionScorer()

    @pytest.fixture
    def filter_config(self):
        return OptionFilterConfig()

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
        greeks = OptionsGreeks(
            delta=Decimal("0.55"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.05"),
            vega=Decimal("0.15"),
            rho=Decimal("0.01"),
        )
        return OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            implied_volatility=Decimal("0.25"),
            greeks=greeks,
            data_quality=OptionDataQualityStatus.GOOD,
        )

    def test_score_good_contract(self, scorer, sample_snapshot, filter_config):
        score, reasons = scorer.score_contract(sample_snapshot, Decimal("150"), filter_config)
        assert score > Decimal("50")
        assert len(reasons) > 0

    def test_score_no_greeks(self, scorer, filter_config):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("5.00"),
            bid_size=Decimal("10"),
            ask_price=Decimal("5.10"),
            ask_size=Decimal("15"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            data_quality=OptionDataQualityStatus.GOOD,
        )
        score, reasons = scorer.score_contract(snap, Decimal("150"), filter_config)
        # Should still score but lower due to missing greeks
        assert score >= Decimal("0")

    def test_score_wide_spread(self, scorer, filter_config):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("3.00"),
            bid_size=Decimal("10"),
            ask_price=Decimal("6.00"),
            ask_size=Decimal("10"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            data_quality=OptionDataQualityStatus.GOOD,
        )
        score, reasons = scorer.score_contract(snap, Decimal("150"), filter_config)
        # Wide spread should result in low score
        assert score < Decimal("50")

    def test_score_zero_bid(self, scorer, filter_config):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
        )
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("0"),
            bid_size=Decimal("0"),
            ask_price=Decimal("5.10"),
            ask_size=Decimal("10"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            data_quality=OptionDataQualityStatus.GOOD,
        )
        score, reasons = scorer.score_contract(snap, Decimal("150"), filter_config)
        assert score == Decimal("0")


class TestSelectBestOption:
    @pytest.fixture
    def risk_budget(self):
        return RiskBudget(
            base_risk_budget=Decimal("1000"),
            adjusted_risk_budget=Decimal("1000"),
            max_position_notional=Decimal("10000"),
            shares=100,
        )

    @pytest.fixture
    def filter_config(self):
        return OptionFilterConfig()

    def test_select_best(self, risk_budget, filter_config):
        scorer = OptionScorer()

        # Create two snapshots with different scores
        def make_snap(strike, bid, ask, delta=Decimal("0.55")):
            strike_int = int(strike)
            contract = OptionContract(
                symbol=f"AAPL240119C{strike_int:08d}",
                underlying_symbol="AAPL",
                option_type=OptionType.CALL,
                expiration_date=date(2024, 1, 19),
                strike_price=strike,
                multiplier=100,
            )
            quote = OptionQuote(
                symbol=contract.symbol,
                timestamp=datetime.now(),
                bid_price=bid,
                bid_size=Decimal("10"),
                ask_price=ask,
                ask_size=Decimal("10"),
            )
            greeks = OptionsGreeks(
                delta=delta,
                gamma=Decimal("0.02"),
                theta=Decimal("-0.05"),
                vega=Decimal("0.15"),
                rho=Decimal("0.01"),
            )
            return OptionMarketSnapshot(
                contract=contract,
                timestamp=datetime.now(),
                quote=quote,
                implied_volatility=Decimal("0.25"),
                greeks=greeks,
                data_quality=OptionDataQualityStatus.GOOD,
            )

        # ATM contract with good delta
        snap1 = make_snap(Decimal("150"), Decimal("5.00"), Decimal("5.10"), Decimal("0.55"))
        # OTM contract with lower delta
        snap2 = make_snap(Decimal("160"), Decimal("2.00"), Decimal("2.10"), Decimal("0.30"))

        best, score, reasons = select_best_option(
            [snap1, snap2],
            Decimal("150"),
            risk_budget,
            filter_config,
            scorer,
        )

        assert best is not None
        assert best.contract.strike_price == Decimal("150")
        assert score > Decimal("0")

    def test_empty_eligible(self, risk_budget, filter_config):
        best, score, reasons = select_best_option(
            [],
            Decimal("150"),
            risk_budget,
            filter_config,
        )
        assert best is None
        assert score == Decimal("0")