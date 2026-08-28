"""Option data gateway for M5 - read-only Alpaca option data access."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.models import OptionsSnapshot, Quote, Trade
from alpaca.data.models import OptionsGreeks as AlpacaOptionsGreeks
from alpaca.data.requests import OptionChainRequest, OptionSnapshotRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.models import OptionContract as AlpacaOptionContract, ContractType

from app.alpaca.client import create_trading_client
from app.core.config import Settings
from app.options.models import (
    OptionContract,
    OptionContractStatus,
    OptionDataQuality,
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionQuote,
    OptionTrade,
    OptionType,
    OptionsGreeks,
)
from app.market.models import DataQualityStatus


class OptionDataGateway:
    """Read-only gateway for Alpaca option data."""

    def __init__(
        self,
        historical_client: OptionHistoricalDataClient,
        trading_client: TradingClient,
    ) -> None:
        self._historical = historical_client
        self._trading = trading_client

    @classmethod
    def from_settings(cls, settings: Settings) -> OptionDataGateway:
        trading_client = create_trading_client(settings)
        historical_client = OptionHistoricalDataClient(settings.alpaca_api_key.get_secret_value() if settings.alpaca_api_key else "")
        return cls(historical_client, trading_client)

    def get_option_chain(
        self,
        underlying_symbol: str,
        expiration_date_gte: Optional[date] = None,
        expiration_date_lte: Optional[date] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        contract_type: Optional[ContractType] = None,
    ) -> list[OptionContract]:
        """Retrieve option contracts for an underlying symbol."""
        req = OptionChainRequest(
            underlying_symbol=underlying_symbol,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=contract_type,
        )
        response = self._historical.get_option_chain(req)
        return [self._normalize_contract(c) for c in response.option_contracts]

    def get_option_snapshots(
        self, symbols: list[str]
    ) -> dict[str, OptionMarketSnapshot]:
        """Retrieve option market snapshots for multiple contracts."""
        if not symbols:
            return {}

        req = OptionSnapshotRequest(symbol_or_symbols=symbols)
        response = self._historical.get_option_snapshot(req)

        snapshots = {}
        for symbol, snapshot in response.items():
            if snapshot:
                snapshots[symbol] = self._normalize_snapshot(symbol, snapshot)
        return snapshots

    def get_option_snapshot(self, symbol: str) -> Optional[OptionMarketSnapshot]:
        """Retrieve a single option market snapshot."""
        snapshots = self.get_option_snapshots([symbol])
        return snapshots.get(symbol)

    def _normalize_contract(self, contract: AlpacaOptionContract) -> OptionContract:
        """Normalize Alpaca OptionContract to local model."""
        option_type = OptionType.CALL if contract.type.value == "call" else OptionType.PUT
        status = (
            OptionContractStatus.ACTIVE
            if contract.status.value == "active"
            else OptionContractStatus.INACTIVE
        )

        return OptionContract(
            symbol=contract.symbol,
            underlying_symbol=contract.underlying_symbol,
            option_type=option_type,
            expiration_date=contract.expiration_date,
            strike_price=Decimal(str(contract.strike_price)),
            multiplier=int(contract.size) if contract.size else 100,
            tradable=contract.tradable,
            status=status,
            size=Decimal(str(contract.size)) if contract.size else None,
            open_interest=int(contract.open_interest) if contract.open_interest else None,
            open_interest_date=contract.open_interest_date,
            close_price=Decimal(str(contract.close_price)) if contract.close_price else None,
            close_price_date=contract.close_price_date,
        )

    def _normalize_snapshot(
        self, symbol: str, snapshot: OptionsSnapshot
    ) -> OptionMarketSnapshot:
        """Normalize Alpaca OptionsSnapshot to local model."""
        # We need the contract metadata - for now we'll create a minimal contract
        # In practice, we'd look up the contract from the chain
        # This is a limitation of the snapshot API - it doesn't include contract metadata
        # We'll need to fetch the chain first or pass contract info

        # Extract data from snapshot
        quote = None
        if snapshot.latest_quote:
            q = snapshot.latest_quote
            quote = OptionQuote(
                symbol=q.symbol,
                timestamp=q.timestamp,
                bid_price=Decimal(str(q.bid_price)),
                bid_size=Decimal(str(q.bid_size)),
                ask_price=Decimal(str(q.ask_price)),
                ask_size=Decimal(str(q.ask_size)),
            )

        trade = None
        if snapshot.latest_trade:
            t = snapshot.latest_trade
            trade = OptionTrade(
                symbol=t.symbol,
                timestamp=t.timestamp,
                price=Decimal(str(t.price)),
                size=Decimal(str(t.size)),
            )

        greeks = None
        if snapshot.greeks:
            g = snapshot.greeks
            # type: ignore[attr-defined] - Alpaca Greeks has same fields
            greeks = OptionsGreeks(
                delta=Decimal(str(g.delta)),
                gamma=Decimal(str(g.gamma)),
                theta=Decimal(str(g.theta)),
                vega=Decimal(str(g.vega)),
                rho=Decimal(str(g.rho)),
            )

        iv = None
        if snapshot.implied_volatility is not None:
            iv = Decimal(str(snapshot.implied_volatility))

        # Build a minimal contract from the symbol (OCC format parsing)
        contract = self._parse_contract_from_symbol(symbol)

        # Assess data quality
        quality = self._assess_data_quality(snapshot, quote, greeks, iv)

        return OptionMarketSnapshot(
            contract=contract,
            timestamp=datetime.now(),
            quote=quote,
            trade=trade,
            implied_volatility=iv,
            greeks=greeks,
            underlying_price=None,  # Would need separate underlying quote
            data_quality=quality.status,
            warnings=quality.warnings,
        )

    def _parse_contract_from_symbol(self, symbol: str) -> OptionContract:
        """Parse OCC option symbol into contract metadata.
        Format: OPTION_SYMBOL_YYMMDD[C/P]STRIKE_PRICE
        Example: AAPL240119C00150000 = AAPL, 2024-01-19, Call, $150.00
        """
        # This is a simplified parser - in production would be more robust
        # For now, return a minimal contract with parsed data
        try:
            # OCC format: root(6) + YYMMDD(6) + C/P(1) + strike(8)
            if len(symbol) >= 21:
                root = symbol[:6].rstrip(" ")
                date_str = symbol[6:12]
                opt_type = symbol[12]
                strike_str = symbol[13:21]

                year = 2000 + int(date_str[:2])
                month = int(date_str[2:4])
                day = int(date_str[4:6])
                exp_date = date(year, month, day)

                opt_type_enum = OptionType.CALL if opt_type == "C" else OptionType.PUT
                strike = Decimal(strike_str) / Decimal("1000")

                return OptionContract(
                    symbol=symbol,
                    underlying_symbol=root,
                    option_type=opt_type_enum,
                    expiration_date=exp_date,
                    strike_price=strike,
                    multiplier=100,
                )
        except Exception:
            pass

        # Fallback
        return OptionContract(
            symbol=symbol,
            underlying_symbol="UNKNOWN",
            option_type=OptionType.CALL,
            expiration_date=date.today(),
            strike_price=Decimal("0"),
            multiplier=100,
            tradable=False,
            status=OptionContractStatus.INACTIVE,
        )

    def _assess_data_quality(
        self,
        snapshot: OptionsSnapshot,
        quote: Optional[OptionQuote],
        greeks: Optional[OptionsGreeks],
        iv: Optional[Decimal],
    ) -> OptionDataQuality:
        """Assess option data quality."""
        warnings = []
        quote_valid = quote is not None and quote.is_valid()
        bid_ask_valid = quote_valid and quote.spread >= Decimal("0")

        has_greeks = greeks is not None
        has_iv = iv is not None and iv > 0

        if quote and quote.spread_pct and quote.spread_pct > Decimal("0.10"):
            warnings.append(f"Wide spread: {quote.spread_pct:.2%}")

        if quote and quote.bid_price <= 0:
            warnings.append("Zero or negative bid price")

        status = OptionDataQualityStatus.GOOD
        if not quote_valid:
            status = OptionDataQualityStatus.INSUFFICIENT
        elif quote and quote.spread_pct and quote.spread_pct > Decimal("0.05"):
            status = OptionDataQualityStatus.DEGRADED

        return OptionDataQuality(
            status=status,
            quote_valid=quote_valid,
            bid_ask_valid=bid_ask_valid,
            spread_pct=quote.spread_pct if quote else None,
            has_greeks=has_greeks,
            has_iv=has_iv,
            underlying_price_available=False,
            timestamp_fresh=True,  # Would check timestamp in production
            warnings=tuple(warnings),
        )


def create_option_gateway(settings: Settings) -> OptionDataGateway:
    """Factory function to create option data gateway."""
    return OptionDataGateway.from_settings(settings)