"""Tests for M5 Option Models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.options.models import (
    InstrumentNoTradeReason,
    OptionContract,
    OptionContractStatus,
    OptionDataQuality,
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionsGreeks,
    OptionTrade,
    OptionType,
)


class TestOptionType:
    def test_option_types(self):
        assert OptionType.CALL == "CALL"
        assert OptionType.PUT == "PUT"


class TestOptionContractStatus:
    def test_statuses(self):
        assert OptionContractStatus.ACTIVE == "ACTIVE"
        assert OptionContractStatus.INACTIVE == "INACTIVE"


class TestOptionDataQualityStatus:
    def test_statuses(self):
        assert OptionDataQualityStatus.GOOD == "GOOD"
        assert OptionDataQualityStatus.DEGRADED == "DEGRADED"
        assert OptionDataQualityStatus.INSUFFICIENT == "INSUFFICIENT"
        assert OptionDataQualityStatus.STALE == "STALE"


class TestOptionContract:
    def test_valid_call_contract(self):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        assert contract.is_call
        assert not contract.is_put
        assert contract.days_to_expiry >= 0

    def test_valid_put_contract(self):
        contract = OptionContract(
            symbol="AAPL240119P00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.PUT,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        assert contract.is_put
        assert not contract.is_call

    def test_expired_contract(self):
        contract = OptionContract(
            symbol="AAPL230119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2023, 1, 19),
            strike_price=Decimal("150"),
            multiplier=100,
        )
        assert contract.days_to_expiry == 0


class TestOptionQuote:
    def test_valid_quote(self):
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("5.00"),
            bid_size=Decimal("10"),
            ask_price=Decimal("5.10"),
            ask_size=Decimal("15"),
        )
        assert quote.is_valid()
        assert quote.spread == Decimal("0.10")
        assert quote.midpoint == Decimal("5.05")
        assert quote.spread_pct is not None

    def test_invalid_quote_negative_spread(self):
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("5.10"),
            bid_size=Decimal("10"),
            ask_price=Decimal("5.00"),
            ask_size=Decimal("15"),
        )
        assert not quote.is_valid()

    def test_zero_bid(self):
        quote = OptionQuote(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            bid_price=Decimal("0"),
            bid_size=Decimal("0"),
            ask_price=Decimal("5.10"),
            ask_size=Decimal("15"),
        )
        assert not quote.is_valid()


class TestOptionTrade:
    def test_trade(self):
        trade = OptionTrade(
            symbol="AAPL240119C00150000",
            timestamp=datetime.now(),
            price=Decimal("5.05"),
            size=Decimal("5"),
        )
        assert trade.price == Decimal("5.05")


class TestOptionsGreeks:
    def test_greeks(self):
        greeks = OptionsGreeks(
            delta=Decimal("0.55"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.05"),
            vega=Decimal("0.15"),
            rho=Decimal("0.01"),
        )
        assert greeks.delta == Decimal("0.55")


class TestOptionMarketSnapshot:
    def test_snapshot_with_quote(self):
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
            implied_volatility=Decimal("0.25"),
        )
        assert snap.reference_price == Decimal("5.05")
        assert snap.premium_per_contract == Decimal("510.00")  # 5.10 * 100
        assert snap.max_loss_per_contract == Decimal("510.00")

    def test_snapshot_without_quote(self):
        contract = OptionContract(
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            option_type=OptionType.CALL,
            expiration_date=date(2024, 1, 19),
            strike_price=Decimal("150"),
        )
        snap = OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
        )
        assert snap.reference_price is None
        assert snap.premium_per_contract is None


class TestOptionDataQuality:
    def test_quality(self):
        quality = OptionDataQuality(
            status=OptionDataQualityStatus.GOOD,
            quote_valid=True,
            bid_ask_valid=True,
            spread_pct=Decimal("0.02"),
            has_greeks=True,
            has_iv=True,
            underlying_price_available=True,
            timestamp_fresh=True,
        )
        assert quality.status == OptionDataQualityStatus.GOOD


class TestInstrumentNoTradeReason:
    def test_reasons(self):
        assert InstrumentNoTradeReason.RISK_REJECTED == "RISK_REJECTED"
        assert InstrumentNoTradeReason.OPTION_PREMIUM_TOO_HIGH == "OPTION_PREMIUM_TOO_HIGH"
        assert InstrumentNoTradeReason.SELECTION_SCORE_TOO_LOW == "SELECTION_SCORE_TOO_LOW"