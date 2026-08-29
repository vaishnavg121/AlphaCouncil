"""Position metrics computation for M7."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.positions.models import (
    ExitDecisionType,
    ExitReasonCode,
    ExitUrgency,
    ManagedPosition,
    PositionSnapshot,
    PositionStatus,
)

if TYPE_CHECKING:
    from app.market.models import MarketState
    from app.risk.models import RiskState


class PositionMetrics:
    """Deterministic position metrics computation."""

    def __init__(self) -> None:
        pass

    def compute_snapshot(
        self,
        position: ManagedPosition,
        market_state: MarketState | None = None,
    ) -> PositionSnapshot:
        """Compute fresh position snapshot with all metrics."""
        # Get fresh price data
        if market_state and market_state.snapshot.quote:
            bid = market_state.snapshot.quote.bid_price
            ask = market_state.snapshot.quote.ask_price
            midpoint = market_state.snapshot.quote.midpoint
        else:
            # Fallback to position's current price
            bid = position.current_price
            ask = position.current_price
            midpoint = position.current_price

        # Compute market value
        market_value = midpoint * position.current_quantity

        # Compute PnL
        if position.side == "LONG":
            unrealized_pnl = (midpoint - position.entry_price) * position.current_quantity
        else:
            unrealized_pnl = (position.entry_price - midpoint) * position.current_quantity

        unrealized_pnl_pct = Decimal("0")
        if position.entry_price > 0:
            if position.side == "LONG":
                unrealized_pnl_pct = (midpoint - position.entry_price) / position.entry_price
            else:
                unrealized_pnl_pct = (position.entry_price - midpoint) / position.entry_price

        # Update watermarks
        highest = position.highest_price_since_entry
        lowest = position.lowest_price_since_entry

        if position.side == "LONG":
            if highest is None or midpoint > highest:
                highest = midpoint
            if lowest is None or midpoint < lowest:
                lowest = midpoint
        else:
            if highest is None or midpoint > highest:
                highest = midpoint
            if lowest is None or midpoint < lowest:
                lowest = midpoint

        # Compute MFE/MAE
        mfe = self._compute_mfe(position, midpoint, highest, lowest)
        mae = self._compute_mae(position, midpoint, highest, lowest)

        # Distance to stop
        distance_to_stop = None
        if position.current_stop_reference and midpoint > 0:
            if position.side == "LONG":
                distance_to_stop = (midpoint - position.current_stop_reference) / midpoint
            else:
                distance_to_stop = (position.current_stop_reference - midpoint) / midpoint

        # Distance to watermarks
        distance_to_high = None
        distance_to_low = None
        if highest and midpoint > 0:
            distance_to_high = (highest - midpoint) / highest
        if lowest and midpoint > 0:
            distance_to_low = (midpoint - lowest) / lowest

        # ATR movement
        atr_movement = None
        if position.initial_stop_reference and market_state and market_state.features.atr_14:
            atr_movement = (midpoint - position.entry_price) / market_state.features.atr_14

        return PositionSnapshot(
            position_id=position.position_id,
            symbol=position.symbol,
            side=position.side,
            instrument_type=position.instrument_type,
            current_quantity=position.current_quantity,
            current_price=midpoint,
            bid_price=bid,
            ask_price=ask,
            midpoint=midpoint,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            entry_price=position.entry_price,
            entry_timestamp=position.entry_timestamp,
            time_in_trade_seconds=position.time_in_trade_seconds,
            highest_price_since_entry=highest,
            lowest_price_since_entry=lowest,
            initial_stop_reference=position.initial_stop_reference,
            current_stop_reference=position.current_stop_reference,
            distance_to_stop_pct=distance_to_stop,
            distance_to_high_watermark_pct=distance_to_high,
            distance_to_low_watermark_pct=distance_to_low,
            mfe=mfe,
            mae=mae,
            atr_at_entry=None,
            current_atr=market_state.features.atr_14 if market_state else None,
            atr_movement_pct=atr_movement,
            data_quality="GOOD",
            snapshot_timestamp=datetime.now(UTC),
        )

    def _compute_mfe(
        self,
        position: ManagedPosition,
        current_price: Decimal,
        highest: Decimal | None,
        lowest: Decimal | None,
    ) -> Decimal:
        """Compute Maximum Favorable Excursion."""
        if position.side == "LONG":
            if highest and highest > position.entry_price:
                return (highest - position.entry_price) / position.entry_price
        else:
            if lowest and lowest < position.entry_price:
                return (position.entry_price - lowest) / position.entry_price
        return Decimal("0")

    def _compute_mae(
        self,
        position: ManagedPosition,
        current_price: Decimal,
        highest: Decimal | None,
        lowest: Decimal | None,
    ) -> Decimal:
        """Compute Maximum Adverse Excursion."""
        if position.side == "LONG":
            if lowest and lowest < position.entry_price:
                return (position.entry_price - lowest) / position.entry_price
        else:
            if highest and highest > position.entry_price:
                return (highest - position.entry_price) / position.entry_price
        return Decimal("0")

    def update_watermarks(
        self,
        position: ManagedPosition,
        current_price: Decimal,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Update high/low watermarks. Returns (new_highest, new_lowest)."""
        highest = position.highest_price_since_entry
        lowest = position.lowest_price_since_entry

        if position.side == "LONG":
            if highest is None or current_price > highest:
                highest = current_price
            if lowest is None or current_price < lowest:
                lowest = current_price
        else:
            if highest is None or current_price > highest:
                highest = current_price
            if lowest is None or current_price < lowest:
                lowest = current_price

        return highest, lowest


class ExitRulesEngine:
    """Deterministic exit rules evaluation engine."""

    def __init__(
        self,
        take_profit_pct: Decimal = Decimal("0.10"),
        trailing_activation_pct: Decimal = Decimal("0.05"),
        trailing_distance_pct: Decimal = Decimal("0.03"),
        max_holding_hours: int = 168,  # 1 week
        option_exit_before_expiry_days: int = 7,
    ) -> None:
        self.take_profit_pct = take_profit_pct
        self.trailing_activation_pct = trailing_activation_pct
        self.trailing_distance_pct = trailing_distance_pct
        self.max_holding_hours = max_holding_hours
        self.option_exit_before_expiry_days = option_exit_before_expiry_days

    def evaluate(
        self,
        position: ManagedPosition,
        snapshot: PositionSnapshot,
        risk_state: RiskState,
        market_state: MarketState | None = None,
    ) -> tuple[list[ExitReasonCode], ExitUrgency, ExitDecisionType]:
        """
        Evaluate all exit rules and return (reason_codes, urgency, decision).
        Priority order: hard rules first, then soft rules.
        """
        reasons: list[ExitReasonCode] = []
        max_urgency = ExitUrgency.NONE
        decision = ExitDecisionType.HOLD

        # Priority 1: Kill switch (IMMEDIATE)
        if risk_state.kill_switch_active:
            reasons.append(ExitReasonCode.KILL_SWITCH)
            max_urgency = ExitUrgency.IMMEDIATE
            decision = ExitDecisionType.EXIT

        # Priority 2: Provider reconciliation safety (IMMEDIATE)
        if position.status == PositionStatus.RECONCILIATION_REQUIRED:
            reasons.append(ExitReasonCode.PROVIDER_RECONCILIATION_REQUIRED)
            if max_urgency != ExitUrgency.IMMEDIATE:
                max_urgency = ExitUrgency.IMMEDIATE
            decision = ExitDecisionType.EXIT

        # Priority 3: M4 risk constitution violation (IMMEDIATE)
        # This would be detected via risk_state or position metrics
        # For now, check if daily loss limit or max drawdown breached
        if risk_state.kill_switch_active:  # Already covered
            pass

        # Priority 4: Hard stop triggered (HIGH)
        if position.current_stop_reference and snapshot.midpoint:
            if position.side == "LONG":
                if snapshot.midpoint <= position.current_stop_reference:
                    reasons.append(ExitReasonCode.HARD_STOP_TRIGGERED)
                    if max_urgency not in (ExitUrgency.IMMEDIATE,):
                        max_urgency = ExitUrgency.HIGH
                    decision = ExitDecisionType.EXIT
            else:
                if snapshot.midpoint >= position.current_stop_reference:
                    reasons.append(ExitReasonCode.HARD_STOP_TRIGGERED)
                    if max_urgency not in (ExitUrgency.IMMEDIATE,):
                        max_urgency = ExitUrgency.HIGH
                    decision = ExitDecisionType.EXIT

        # Priority 5: Max loss reached (HIGH)
        max_loss_pct = abs(position.unrealized_pnl_pct)
        # Use risk budget at entry as max allowed loss reference
        if position.risk_budget_at_entry > 0:
            notional = position.current_notional
            if notional > 0:
                loss_pct = abs(position.unrealized_pnl) / notional
                if loss_pct >= Decimal("1.0"):  # 100% of risk budget = max loss
                    reasons.append(ExitReasonCode.MAX_LOSS_REACHED)
                    if max_urgency not in (ExitUrgency.IMMEDIATE, ExitUrgency.HIGH):
                        max_urgency = ExitUrgency.HIGH
                    decision = ExitDecisionType.EXIT

        # Priority 6: Option expiry approaching (HIGH)
        if position.instrument_type == "OPTION":
            # Would need option expiry data in position
            # Placeholder for when option support is added
            pass

        # Priority 7: Max holding period (NORMAL)
        if position.time_in_trade_seconds >= self.max_holding_hours * 3600:
            reasons.append(ExitReasonCode.MAX_HOLDING_PERIOD)
            if max_urgency not in (ExitUrgency.IMMEDIATE, ExitUrgency.HIGH):
                max_urgency = ExitUrgency.NORMAL
            decision = ExitDecisionType.EXIT

        # Priority 8: Trailing stop (NORMAL)
        if position.side == "LONG" and position.highest_price_since_entry and snapshot.midpoint is not None:
            gain_from_entry = (snapshot.midpoint - position.entry_price) / position.entry_price
            if gain_from_entry >= self.trailing_activation_pct:
                trailing_stop = position.highest_price_since_entry * (Decimal("1") - self.trailing_distance_pct)
                if snapshot.midpoint <= trailing_stop:
                    reasons.append(ExitReasonCode.TRAILING_STOP_TRIGGERED)
                    if max_urgency not in (ExitUrgency.IMMEDIATE, ExitUrgency.HIGH):
                        max_urgency = ExitUrgency.NORMAL
                    decision = ExitDecisionType.EXIT

        elif position.side == "SHORT" and position.lowest_price_since_entry and snapshot.midpoint is not None:
            gain_from_entry = (position.entry_price - snapshot.midpoint) / position.entry_price
            if gain_from_entry >= self.trailing_activation_pct:
                trailing_stop = position.lowest_price_since_entry * (Decimal("1") + self.trailing_distance_pct)
                if snapshot.midpoint >= trailing_stop:
                    reasons.append(ExitReasonCode.TRAILING_STOP_TRIGGERED)
                    if max_urgency not in (ExitUrgency.IMMEDIATE, ExitUrgency.HIGH):
                        max_urgency = ExitUrgency.NORMAL
                    decision = ExitDecisionType.EXIT

        # Priority 9: Take profit (NORMAL)
        if snapshot.unrealized_pnl_pct >= self.take_profit_pct:
            reasons.append(ExitReasonCode.TAKE_PROFIT)
            if max_urgency not in (ExitUrgency.IMMEDIATE, ExitUrgency.HIGH):
                max_urgency = ExitUrgency.NORMAL
            decision = ExitDecisionType.EXIT

        # Priority 10: Thesis deterioration (NORMAL)
        if market_state and market_state.features:
            # Trend reversal detection
            if position.side == "LONG" and market_state.features.trend_short in ("DOWN", "STRONG_DOWN"):
                reasons.append(ExitReasonCode.TREND_REVERSAL)
                if max_urgency == ExitUrgency.NONE:
                    max_urgency = ExitUrgency.NORMAL
                decision = ExitDecisionType.EXIT
            elif position.side == "SHORT" and market_state.features.trend_short in ("UP", "STRONG_UP"):
                reasons.append(ExitReasonCode.TREND_REVERSAL)
                if max_urgency == ExitUrgency.NONE:
                    max_urgency = ExitUrgency.NORMAL
                decision = ExitDecisionType.EXIT

            # Momentum reversal
            if position.side == "LONG" and market_state.features.momentum_5d and market_state.features.momentum_5d < Decimal("-0.05"):
                reasons.append(ExitReasonCode.MOMENTUM_REVERSAL)
                if max_urgency == ExitUrgency.NONE:
                    max_urgency = ExitUrgency.NORMAL
                decision = ExitDecisionType.EXIT
            elif position.side == "SHORT" and market_state.features.momentum_5d and market_state.features.momentum_5d > Decimal("0.05"):
                reasons.append(ExitReasonCode.MOMENTUM_REVERSAL)
                if max_urgency == ExitUrgency.NONE:
                    max_urgency = ExitUrgency.NORMAL
                decision = ExitDecisionType.EXIT

            # Volatility spike
            if market_state.features.realized_vol_20 and market_state.features.realized_vol_20 > Decimal("0.05"):
                reasons.append(ExitReasonCode.VOLATILITY_SPIKE)
                if max_urgency == ExitUrgency.NONE:
                    max_urgency = ExitUrgency.NORMAL
                decision = ExitDecisionType.EXIT

        return reasons, max_urgency, decision


def create_position_metrics() -> PositionMetrics:
    return PositionMetrics()


def create_exit_rules_engine(
    take_profit_pct: Decimal | None = None,
    trailing_activation_pct: Decimal | None = None,
    trailing_distance_pct: Decimal | None = None,
    max_holding_hours: int | None = None,
    option_exit_before_expiry_days: int | None = None,
) -> ExitRulesEngine:
    return ExitRulesEngine(
        take_profit_pct=take_profit_pct or Decimal("0.10"),
        trailing_activation_pct=trailing_activation_pct or Decimal("0.05"),
        trailing_distance_pct=trailing_distance_pct or Decimal("0.03"),
        max_holding_hours=max_holding_hours or 168,
        option_exit_before_expiry_days=option_exit_before_expiry_days or 7,
    )