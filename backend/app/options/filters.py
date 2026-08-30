"""Option contract filtering logic for M5.

Deterministic filters for expiry, moneyness, liquidity, and affordability.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.options.models import (
    OptionContract,
    OptionMarketSnapshot,
    OptionType,
)
from app.risk.models import RiskBudget


class OptionFilterConfig(BaseModel):
    """Configuration for option filtering."""

    model_config = ConfigDict(frozen=True)

    # Expiry filters
    min_dte: int = 7
    target_dte_min: int = 21
    target_dte_max: int = 60
    max_dte: int = 90

    # Moneyness filters (for CALLs: spot/strike, for PUTs: strike/spot)
    min_moneyness_pct: Decimal = Decimal("0.85")  # 85% moneyness minimum
    max_moneyness_pct: Decimal = Decimal("1.15")  # 115% moneyness maximum
    target_moneyness_min: Decimal = Decimal("0.95")  # Near ATM preferred
    target_moneyness_max: Decimal = Decimal("1.05")

    # Delta filters (if available)
    target_abs_delta_min: Decimal = Decimal("0.40")
    target_abs_delta_max: Decimal = Decimal("0.75")
    hard_abs_delta_min: Decimal = Decimal("0.25")
    hard_abs_delta_max: Decimal = Decimal("0.90")

    # Liquidity filters
    max_spread_pct: Decimal = Decimal("0.10")  # 10% max spread
    preferred_spread_pct: Decimal = Decimal("0.03")  # 3% preferred
    min_bid_size: int = 1
    min_ask_size: int = 1
    reject_zero_bid: bool = True

    # Affordability
    max_option_contracts_per_plan: int = 10

    # Data quality
    require_greeks: bool = False
    require_iv: bool = False
    max_data_age_hours: int = 24


class OptionFilters:
    """Deterministic option contract filters."""

    def __init__(self, config: OptionFilterConfig | None = None) -> None:
        self.config = config or OptionFilterConfig()

    def filter_by_expiry(
        self, contracts: list[OptionContract], reference_date: date | None = None
    ) -> tuple[list[OptionContract], int]:
        """Filter contracts by DTE range."""
        if reference_date is None:
            reference_date = date.today()

        eligible = []
        rejected = 0
        for contract in contracts:
            dte = (contract.expiration_date - reference_date).days
            if dte < self.config.min_dte or dte > self.config.max_dte:
                rejected += 1
                continue
            eligible.append(contract)
        return eligible, rejected

    def filter_by_moneyness(
        self,
        contracts: list[OptionContract],
        underlying_price: Decimal,
    ) -> tuple[list[OptionContract], int]:
        """Filter contracts by moneyness range."""
        if underlying_price <= 0:
            return [], len(contracts)

        eligible = []
        rejected = 0
        for contract in contracts:
            if contract.option_type == OptionType.CALL:
                moneyness = underlying_price / contract.strike_price
            else:
                moneyness = contract.strike_price / underlying_price

            if (
                moneyness < self.config.min_moneyness_pct
                or moneyness > self.config.max_moneyness_pct
            ):
                rejected += 1
                continue
            eligible.append(contract)
        return eligible, rejected

    def filter_by_delta(
        self,
        snapshots: list[OptionMarketSnapshot],
    ) -> tuple[list[OptionMarketSnapshot], int]:
        """Filter by delta if available."""
        eligible = []
        rejected = 0
        for snap in snapshots:
            if not snap.greeks:
                # If delta unavailable and not required, pass through
                if not self.config.require_greeks:
                    eligible.append(snap)
                else:
                    rejected += 1
                continue

            abs_delta = abs(snap.greeks.delta)
            if (
                abs_delta < self.config.hard_abs_delta_min
                or abs_delta > self.config.hard_abs_delta_max
            ):
                rejected += 1
                continue
            eligible.append(snap)
        return eligible, rejected

    def filter_by_liquidity(
        self,
        snapshots: list[OptionMarketSnapshot],
    ) -> tuple[list[OptionMarketSnapshot], int]:
        """Filter by spread and quote validity."""
        eligible = []
        rejected = 0
        for snap in snapshots:
            if not snap.quote:
                rejected += 1
                continue

            q = snap.quote
            if not q.is_valid():
                rejected += 1
                continue

            if self.config.reject_zero_bid and q.bid_price <= 0:
                rejected += 1
                continue

            if q.bid_size < self.config.min_bid_size or q.ask_size < self.config.min_ask_size:
                rejected += 1
                continue

            if q.spread_pct and q.spread_pct > self.config.max_spread_pct:
                rejected += 1
                continue

            eligible.append(snap)
        return eligible, rejected

    def filter_by_affordability(
        self,
        snapshots: list[OptionMarketSnapshot],
        risk_budget: RiskBudget,
    ) -> tuple[list[OptionMarketSnapshot], int]:
        """Filter contracts that fit within risk budget."""
        if risk_budget.adjusted_risk_budget <= 0:
            return [], len(snapshots)

        eligible = []
        rejected = 0
        for snap in snapshots:
            premium = snap.premium_per_contract
            if premium is None:
                rejected += 1
                continue

            if premium > risk_budget.adjusted_risk_budget:
                rejected += 1
                continue

            max_contracts = int(risk_budget.adjusted_risk_budget / premium)
            max_contracts = min(max_contracts, self.config.max_option_contracts_per_plan)

            if max_contracts < 1:
                rejected += 1
                continue

            eligible.append(snap)
        return eligible, rejected


def apply_option_filters(
    chain: list[OptionContract],
    snapshots: dict[str, OptionMarketSnapshot],
    underlying_price: Decimal,
    risk_budget: RiskBudget,
    config: OptionFilterConfig | None = None,
) -> tuple[list[OptionMarketSnapshot], dict[str, int]]:
    """Apply all filters to option chain and return eligible contracts with stats."""
    filters = OptionFilters(config)
    stats = {
        "total_retrieved": len(chain),
        "expired_out_of_range": 0,
        "moneyness_out_of_range": 0,
        "delta_out_of_range": 0,
        "spread_too_wide": 0,
        "premium_too_high": 0,
        "invalid_quote": 0,
        "zero_bid": 0,
        "non_tradable": 0,
        "eligible": 0,
    }

    # Filter by expiry
    chain, rejected = filters.filter_by_expiry(chain)
    stats["expired_out_of_range"] = rejected

    # Filter by moneyness
    chain, rejected = filters.filter_by_moneyness(chain, underlying_price)
    stats["moneyness_out_of_range"] = rejected

    # Get snapshots for remaining contracts
    contract_symbols = [c.symbol for c in chain]
    contract_snapshots = [snapshots[s] for s in contract_symbols if s in snapshots]

    # Filter by delta
    contract_snapshots, rejected = filters.filter_by_delta(contract_snapshots)
    stats["delta_out_of_range"] = rejected

    # Filter by liquidity
    contract_snapshots, rejected = filters.filter_by_liquidity(contract_snapshots)
    stats["invalid_quote"] = rejected  # Includes spread, bid/ask, sizes

    # Filter by affordability
    contract_snapshots, rejected = filters.filter_by_affordability(
        contract_snapshots, risk_budget
    )
    stats["premium_too_high"] = rejected

    stats["eligible"] = len(contract_snapshots)
    return contract_snapshots, stats