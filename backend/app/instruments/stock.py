"""Equity instrument planning for M5.

Deterministic stock/ETF position planning within M4 risk ceilings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.instruments.models import EquityInstrumentPlan, EquitySide
from app.market.models import MarketState
from app.risk.models import RiskBudget, RiskEvaluation


class EquityPlanner:
    """Deterministic equity position planning."""

    def __init__(
        self,
        max_position_notional_pct: Decimal = Decimal("0.10"),
        fractional_supported: bool = True,
    ) -> None:
        self.max_position_notional_pct = max_position_notional_pct
        self.fractional_supported = fractional_supported

    def calculate_plan(
        self,
        market_state: MarketState,
        risk_evaluation: RiskEvaluation,
        thesis_direction: str,  # "BULLISH" or "BEARISH"
    ) -> Optional[EquityInstrumentPlan]:
        """Calculate equity instrument plan from market state and risk evaluation."""
        risk_budget = risk_evaluation.risk_budget
        if not risk_budget:
            return None

        ref_price = self._get_reference_price(market_state)
        if ref_price <= 0:
            return None

        # Determine side
        if thesis_direction == "BULLISH":
            side = EquitySide.LONG
        elif thesis_direction == "BEARISH":
            side = EquitySide.SHORT
        else:
            return None

        # Maximum notional from M4
        max_notional = risk_budget.max_position_notional

        # Target notional based on risk budget and provisional stop
        if risk_budget.atr_stop_distance and risk_budget.atr_stop_distance > 0:
            stop_distance_pct = risk_budget.atr_stop_distance / ref_price
            target_notional = risk_budget.adjusted_risk_budget / stop_distance_pct
        else:
            # Fallback: use min stop distance from constitution
            from app.risk.constitution import CONSTITUTION
            stop_distance_pct = CONSTITUTION.MIN_STOP_DISTANCE_PCT
            target_notional = risk_budget.adjusted_risk_budget / stop_distance_pct

        # Cap at M4 ceiling
        planned_notional = min(target_notional, max_notional)

        # Calculate quantity
        if self.fractional_supported:
            estimated_quantity = planned_notional / ref_price
        else:
            estimated_quantity = Decimal(str(int(planned_notional / ref_price)))
            if estimated_quantity < 1:
                return None
            planned_notional = estimated_quantity * ref_price

        # Estimated loss at provisional stop
        estimated_loss_at_risk_stop = planned_notional * stop_distance_pct

        # Verify within risk budget
        if estimated_loss_at_risk_stop > risk_budget.adjusted_risk_budget + Decimal("0.01"):
            # Reduce quantity to fit
            if self.fractional_supported:
                planned_notional = risk_budget.adjusted_risk_budget / stop_distance_pct
                estimated_quantity = planned_notional / ref_price
            else:
                estimated_quantity = Decimal(str(int(risk_budget.adjusted_risk_budget / (ref_price * stop_distance_pct))))
                if estimated_quantity < 1:
                    return None
                planned_notional = estimated_quantity * ref_price
            estimated_loss_at_risk_stop = planned_notional * stop_distance_pct

        risk_budget_used = estimated_loss_at_risk_stop

        # Selection score for equity (simpler scoring)
        score = self._calculate_equity_score(market_state, risk_budget)

        reasons = (
            f"ref_price={ref_price}",
            f"planned_notional={planned_notional}",
            f"estimated_qty={estimated_quantity}",
            f"stop_distance_pct={stop_distance_pct:.2%}",
            f"risk_budget_used={risk_budget_used}",
        )

        return EquityInstrumentPlan(
            symbol=market_state.symbol,
            side=side,
            reference_price=ref_price,
            max_notional=max_notional,
            planned_notional=planned_notional,
            estimated_quantity=estimated_quantity,
            fractional_supported=self.fractional_supported,
            risk_budget_used=risk_budget_used,
            estimated_loss_at_risk_stop=estimated_loss_at_risk_stop,
            selection_score=score,
            selection_reasons=reasons,
        )

    def _get_reference_price(self, market_state: MarketState) -> Decimal:
        """Get reference price for equity."""
        if market_state.snapshot.quote:
            return market_state.snapshot.quote.midpoint
        if market_state.snapshot.trade:
            return market_state.snapshot.trade.price
        if market_state.latest_bar:
            return market_state.latest_bar.close
        if market_state.snapshot.daily_bar:
            return market_state.snapshot.daily_bar.close
        return Decimal("0")

    def _calculate_equity_score(
        self,
        market_state: MarketState,
        risk_budget: RiskBudget,
    ) -> Decimal:
        """Calculate selection score for equity alternative."""
        score = Decimal("50")  # Base score

        # Data quality bonus
        if market_state.data_quality.status == "GOOD":
            score += Decimal("20")
        elif market_state.data_quality.status == "DEGRADED":
            score += Decimal("10")

        # Liquidity bonus
        if market_state.features.avg_volume_20 and market_state.features.avg_volume_20 > Decimal("1000000"):
            score += Decimal("15")

        # Tight spread bonus
        if market_state.snapshot.quote and market_state.snapshot.quote.spread:
            mid = market_state.snapshot.quote.midpoint
            if mid > 0:
                spread_pct = market_state.snapshot.quote.spread / mid
                if spread_pct < Decimal("0.01"):
                    score += Decimal("10")
                elif spread_pct < Decimal("0.02"):
                    score += Decimal("5")

        # Risk budget utilization efficiency
        if risk_budget.adjusted_risk_budget > 0:
            utilization = risk_budget.adjusted_risk_budget / risk_budget.base_risk_budget
            if utilization >= Decimal("0.8"):
                score += Decimal("10")

        # Cap at 100
        return min(score, Decimal("100"))