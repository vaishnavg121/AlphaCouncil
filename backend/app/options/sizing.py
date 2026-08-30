"""Option position sizing for M5.

Deterministic calculation of contract quantities within M4 risk budget.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.options.models import OptionMarketSnapshot
from app.risk.models import RiskBudget

if TYPE_CHECKING:
    from app.instruments.models import OptionInstrumentPlan


class OptionSizer:
    """Deterministic option position sizing."""

    def __init__(self, max_contracts_per_plan: int = 10) -> None:
        self.max_contracts_per_plan = max_contracts_per_plan

    def calculate_plan(
        self,
        snap: OptionMarketSnapshot,
        risk_budget: RiskBudget,
        selection_score: Decimal,
        selection_reasons: tuple[str, ...],
        warnings: tuple[str, ...] = (),
    ) -> OptionInstrumentPlan | None:
        """Calculate option instrument plan from snapshot and risk budget."""
        from app.instruments.models import OptionInstrumentPlan

        premium = snap.premium_per_contract
        if premium is None or premium <= 0:
            return None

        # Maximum contracts that fit in risk budget
        max_contracts = int(risk_budget.adjusted_risk_budget / premium)
        max_contracts = min(max_contracts, self.max_contracts_per_plan)

        if max_contracts < 1:
            return None

        # For M5, we use the maximum affordable contracts
        # Future versions could implement utilization targets < 100%
        planned_contracts = max_contracts

        total_premium = premium * Decimal(str(planned_contracts))
        maximum_loss = total_premium  # For long options, max loss = premium paid

        # Verify invariant
        if maximum_loss > risk_budget.adjusted_risk_budget + Decimal("0.01"):
            return None

        risk_budget_used = maximum_loss
        utilization_pct = (risk_budget_used / risk_budget.adjusted_risk_budget) * Decimal("100")

        if snap.quote is None:
            return None

        q = snap.quote
        return OptionInstrumentPlan(
            contract_symbol=snap.contract.symbol,
            underlying_symbol=snap.contract.underlying_symbol,
            option_type=snap.contract.option_type,
            expiration_date=snap.contract.expiration_date,
            days_to_expiry=snap.contract.days_to_expiry,
            strike_price=snap.contract.strike_price,
            bid_price=q.bid_price,
            ask_price=q.ask_price,
            midpoint=q.midpoint,
            spread=q.spread,
            spread_pct=q.spread_pct or Decimal("0"),
            implied_volatility=snap.implied_volatility,
            delta=snap.greeks.delta if snap.greeks else None,
            gamma=snap.greeks.gamma if snap.greeks else None,
            theta=snap.greeks.theta if snap.greeks else None,
            vega=snap.greeks.vega if snap.greeks else None,
            premium_per_contract=premium,
            multiplier=snap.contract.multiplier,
            planned_contracts=planned_contracts,
            total_premium=total_premium,
            maximum_loss=maximum_loss,
            risk_budget_used=risk_budget_used,
            selection_score=selection_score,
            selection_reasons=selection_reasons,
            warnings=warnings + (
                f"risk_budget_utilization={utilization_pct:.1f}%",
            ),
        )