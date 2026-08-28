"""Risk Rules Engine - Deterministic implementation of all risk checks.

ZERO LLM calls. Pure deterministic computation.
Fail-closed: any calculation error => REJECTED.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.risk.constitution import CONSTITUTION, RiskConstitution
from app.risk.models import (
    RiskCheckResult,
    RiskContext,
    RiskReasonCode,
    RiskRuleType,
)

if TYPE_CHECKING:
    from app.risk.models import RiskBudget, RiskEvaluation


class RiskRulesEngine:
    """Deterministic risk rules evaluation engine."""

    def __init__(self, constitution: RiskConstitution = CONSTITUTION) -> None:
        self.constitution = constitution

    def evaluate_all(self, ctx: RiskContext) -> tuple[RiskCheckResult, ...]:
        """Run all risk checks in deterministic order.

        Order: Hard gates first (fail-fast), then soft reductions.
        """
        checks: list[RiskCheckResult] = []

        # --- HARD GATES (fail-fast) ---
        # 1. Kill switch
        checks.append(self._check_kill_switch(ctx))

        # 2. M3 NO_TRADE gate
        checks.append(self._check_m3_no_trade(ctx))

        # 3. TradeThesis validation
        checks.append(self._check_thesis_valid(ctx))

        # 4. Data quality gate
        checks.append(self._check_data_quality(ctx))

        # 5. Committee confidence gate
        checks.append(self._check_committee_confidence(ctx))

        # 6. Price validation
        checks.append(self._check_price_valid(ctx))

        # 7. Daily loss limit
        checks.append(self._check_daily_loss(ctx))

        # 8. Max drawdown
        checks.append(self._check_max_drawdown(ctx))

        # If any hard gate failed, we can stop (fail-fast)
        # But we continue to collect all violations for observability
        hard_failures = [c for c in checks if c.is_hard_rejection]

        # --- SOFT REDUCTIONS (only if no hard failure) ---
        if not hard_failures:
            # 9. Volatility reduction
            checks.append(self._check_volatility(ctx))

            # 10. Liquidity reduction
            checks.append(self._check_liquidity(ctx))

            # 11. Confidence reduction (additional to hard gate)
            checks.append(self._check_confidence_reduction(ctx))

            # 12. Symbol concentration
            checks.append(self._check_symbol_concentration(ctx))

            # 13. Gross exposure
            checks.append(self._check_gross_exposure(ctx))

            # 14. Net exposure
            checks.append(self._check_net_exposure(ctx))

            # 15. Max positions
            checks.append(self._check_max_positions(ctx))

            # 16. Group concentration (placeholder - requires sector mapping)
            checks.append(self._check_group_concentration(ctx))

            # 17. Correlation redundancy (placeholder)
            checks.append(self._check_correlation_redundancy(ctx))

        return tuple(checks)

    # ============================================================
    # HARD GATE CHECKS
    # ============================================================

    def _check_kill_switch(self, ctx: RiskContext) -> RiskCheckResult:
        if ctx.risk_state.kill_switch_active:
            return RiskCheckResult(
                rule_name="kill_switch",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.KILL_SWITCH_ACTIVE,
                detail=f"Kill switch active: {ctx.risk_state.kill_switch_reason}",
            )
        return RiskCheckResult(
            rule_name="kill_switch",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_m3_no_trade(self, ctx: RiskContext) -> RiskCheckResult:
        decision = ctx.trade_thesis.committee_decision.decision
        if decision.value == "NO_TRADE":
            no_trade_reason = ctx.trade_thesis.committee_decision.no_trade_reason
            detail = f"M3 NO_TRADE: {no_trade_reason.value if no_trade_reason else 'unknown'}"
            return RiskCheckResult(
                rule_name="m3_no_trade",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.M3_NO_TRADE,
                detail=detail,
            )
        return RiskCheckResult(
            rule_name="m3_no_trade",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_thesis_valid(self, ctx: RiskContext) -> RiskCheckResult:
        thesis = ctx.trade_thesis
        errors = []

        if not thesis.symbol:
            errors.append("missing symbol")
        if not thesis.proposed_direction:
            errors.append("missing direction")
        if thesis.committee_confidence is None:
            errors.append("missing committee_confidence")
        elif thesis.committee_confidence < 0 or thesis.committee_confidence > 1:
            errors.append("invalid committee_confidence range")
        if not thesis.committee_decision:
            errors.append("missing committee_decision")
        if thesis.committee_confidence == 0:
            errors.append("zero committee_confidence")

        if errors:
            return RiskCheckResult(
                rule_name="thesis_validation",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.INVALID_THESIS,
                detail=f"Invalid thesis: {'; '.join(errors)}",
            )
        return RiskCheckResult(
            rule_name="thesis_validation",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_data_quality(self, ctx: RiskContext) -> RiskCheckResult:
        # Check if we have minimum required market data
        if ctx.reference_price <= 0:
            return RiskCheckResult(
                rule_name="data_quality",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.POOR_DATA_QUALITY,
                detail="Reference price missing or invalid",
            )

        # Check data quality from thesis evidence packet
        dq_status = ctx.trade_thesis.committee_decision  # This doesn't have dq directly
        # Check from evidence packet if available
        evidence = ctx.trade_thesis.committee_decision  # TradeThesis has committee_decision
        # The evidence packet is in CommitteeResult, not directly in TradeThesis
        # For now, we check the reference price validity

        return RiskCheckResult(
            rule_name="data_quality",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_committee_confidence(self, ctx: RiskContext) -> RiskCheckResult:
        conf = ctx.trade_thesis.committee_confidence
        min_conf = self.constitution.HARD_GATES[
            [g.name for g in self.constitution.HARD_GATES].index("low_committee_confidence")
        ].threshold

        if conf < min_conf:
            return RiskCheckResult(
                rule_name="committee_confidence",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.LOW_COMMITTEE_CONFIDENCE,
                detail=f"Committee confidence {conf:.2%} below minimum {min_conf:.0%}",
            )
        return RiskCheckResult(
            rule_name="committee_confidence",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_price_valid(self, ctx: RiskContext) -> RiskCheckResult:
        # Check reference price
        if ctx.reference_price <= 0:
            return RiskCheckResult(
                rule_name="price_validation",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.INVALID_PRICE,
                detail=f"Invalid reference price: {ctx.reference_price}",
            )

        # Check bid/ask spread if available
        if ctx.bid_price is not None and ctx.ask_price is not None:
            if ctx.bid_price <= 0 or ctx.ask_price <= 0:
                return RiskCheckResult(
                    rule_name="price_validation",
                    rule_type=RiskRuleType.HARD_GATE,
                    passed=False,
                    reason_code=RiskReasonCode.INVALID_PRICE,
                    detail=f"Invalid bid/ask: bid={ctx.bid_price}, ask={ctx.ask_price}",
                )
            if ctx.ask_price < ctx.bid_price:
                return RiskCheckResult(
                    rule_name="price_validation",
                    rule_type=RiskRuleType.HARD_GATE,
                    passed=False,
                    reason_code=RiskReasonCode.INVALID_PRICE,
                    detail=f"Negative spread: bid={ctx.bid_price}, ask={ctx.ask_price}",
                )
            # Check spread percentage
            mid = (ctx.bid_price + ctx.ask_price) / Decimal("2")
            if mid > 0:
                spread_pct = (ctx.ask_price - ctx.bid_price) / mid
                if spread_pct > Decimal("0.05"):  # 5% max spread
                    return RiskCheckResult(
                        rule_name="price_validation",
                        rule_type=RiskRuleType.HARD_GATE,
                        passed=False,
                        reason_code=RiskReasonCode.INVALID_PRICE,
                        detail=f"Spread too wide: {spread_pct:.2%}",
                    )

        return RiskCheckResult(
            rule_name="price_validation",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_daily_loss(self, ctx: RiskContext) -> RiskCheckResult:
        daily_loss_limit = self.constitution.HARD_GATES[
            [g.name for g in self.constitution.HARD_GATES].index("daily_loss_limit")
        ].threshold

        daily_return = ctx.risk_state.daily_return
        if daily_return < -daily_loss_limit:
            return RiskCheckResult(
                rule_name="daily_loss_limit",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.DAILY_LOSS_LIMIT,
                detail=f"Daily loss {daily_return:.2%} exceeds limit {daily_loss_limit:.0%}",
            )
        return RiskCheckResult(
            rule_name="daily_loss_limit",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    def _check_max_drawdown(self, ctx: RiskContext) -> RiskCheckResult:
        max_dd = self.constitution.HARD_GATES[
            [g.name for g in self.constitution.HARD_GATES].index("max_drawdown")
        ].threshold

        current_dd = ctx.risk_state.current_drawdown
        if current_dd > max_dd:
            return RiskCheckResult(
                rule_name="max_drawdown",
                rule_type=RiskRuleType.HARD_GATE,
                passed=False,
                reason_code=RiskReasonCode.MAX_DRAWDOWN,
                detail=f"Drawdown {current_dd:.2%} exceeds limit {max_dd:.0%}",
            )
        return RiskCheckResult(
            rule_name="max_drawdown",
            rule_type=RiskRuleType.HARD_GATE,
            passed=True,
        )

    # ============================================================
    # SOFT REDUCTION CHECKS
    # ============================================================

    def _check_volatility(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("volatility_reduction")
        if not limit:
            return RiskCheckResult(rule_name="volatility", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        if ctx.realized_vol_20 is None:
            return RiskCheckResult(rule_name="volatility", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        if ctx.realized_vol_20 > limit.threshold:
            # Proportional reduction beyond threshold
            excess = ctx.realized_vol_20 - limit.threshold
            reduction = max(limit.reduction_factor, Decimal("1") - excess * self.constitution.VOLATILITY_REDUCTION_SLOPE)
            reduction = max(reduction, Decimal("0.1"))  # Floor at 10%
            return RiskCheckResult(
                rule_name="volatility",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.VOLATILITY_REDUCTION,
                detail=f"Volatility {ctx.realized_vol_20:.2%} exceeds {limit.threshold:.0%}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="volatility",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_liquidity(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("liquidity_reduction")
        if not limit:
            return RiskCheckResult(rule_name="liquidity", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        if ctx.avg_dollar_volume_20 is None:
            return RiskCheckResult(rule_name="liquidity", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        if ctx.avg_dollar_volume_20 < limit.threshold:
            # Proportional reduction
            ratio = ctx.avg_dollar_volume_20 / limit.threshold
            reduction = max(limit.reduction_factor, ratio)
            reduction = max(reduction, Decimal("0.1"))
            return RiskCheckResult(
                rule_name="liquidity",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.LIQUIDITY_REDUCTION,
                detail=f"Avg dollar volume ${ctx.avg_dollar_volume_20:,.0f} below ${limit.threshold:,.0f}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="liquidity",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_confidence_reduction(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("confidence_reduction")
        if not limit:
            return RiskCheckResult(rule_name="confidence_reduction", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        conf = ctx.trade_thesis.committee_confidence
        if conf < limit.threshold:
            # Linear reduction from 1.0 at 100% to reduction_factor at threshold
            # Below threshold, use reduction_factor
            reduction = limit.reduction_factor
            return RiskCheckResult(
                rule_name="confidence_reduction",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.CONFIDENCE_REDUCTION,
                detail=f"Committee confidence {conf:.2%} below {limit.threshold:.0%}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="confidence_reduction",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_symbol_concentration(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("symbol_concentration")
        if not limit:
            return RiskCheckResult(rule_name="symbol_concentration", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        existing = ctx.portfolio.get_position(ctx.trade_thesis.symbol)
        if existing is None:
            return RiskCheckResult(rule_name="symbol_concentration", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        equity = ctx.equity
        if equity <= 0:
            return RiskCheckResult(rule_name="symbol_concentration", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        existing_pct = existing.notional / equity
        if existing_pct > limit.threshold:
            # Reduce proportionally
            reduction = max(limit.reduction_factor, Decimal("1") - (existing_pct - limit.threshold) * Decimal("10"))
            reduction = max(reduction, Decimal("0.1"))
            return RiskCheckResult(
                rule_name="symbol_concentration",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.SYMBOL_CONCENTRATION,
                detail=f"Existing {ctx.trade_thesis.symbol} exposure {existing_pct:.2%} exceeds {limit.threshold:.0%}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="symbol_concentration",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_gross_exposure(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("gross_exposure")
        if not limit:
            return RiskCheckResult(rule_name="gross_exposure", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        equity = ctx.equity
        if equity <= 0:
            return RiskCheckResult(rule_name="gross_exposure", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        max_gross = equity * self.constitution.MAX_GROSS_EXPOSURE_PCT
        current_gross = ctx.portfolio.gross_exposure
        threshold_amt = max_gross * limit.threshold

        if current_gross > threshold_amt:
            reduction = max(limit.reduction_factor, Decimal("1") - (current_gross - threshold_amt) / max_gross)
            reduction = max(reduction, Decimal("0.1"))
            return RiskCheckResult(
                rule_name="gross_exposure",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.GROSS_EXPOSURE,
                detail=f"Gross exposure ${current_gross:,.0f} exceeds {limit.threshold:.0%} of limit ${max_gross:,.0f}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="gross_exposure",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_net_exposure(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("net_exposure")
        if not limit:
            return RiskCheckResult(rule_name="net_exposure", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        equity = ctx.equity
        if equity <= 0:
            return RiskCheckResult(rule_name="net_exposure", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        max_net = equity * self.constitution.MAX_NET_EXPOSURE_PCT
        current_net = abs(ctx.portfolio.net_exposure)
        threshold_amt = max_net * limit.threshold

        if current_net > threshold_amt:
            reduction = max(limit.reduction_factor, Decimal("1") - (current_net - threshold_amt) / max_net)
            reduction = max(reduction, Decimal("0.1"))
            return RiskCheckResult(
                rule_name="net_exposure",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.NET_EXPOSURE,
                detail=f"Net exposure ${current_net:,.0f} exceeds {limit.threshold:.0%} of limit ${max_net:,.0f}",
                reduction_factor=reduction,
            )
        return RiskCheckResult(
            rule_name="net_exposure",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_max_positions(self, ctx: RiskContext) -> RiskCheckResult:
        limit = self.constitution.get_soft_limit("max_positions")
        if not limit:
            return RiskCheckResult(rule_name="max_positions", rule_type=RiskRuleType.SOFT_REDUCTION, passed=True)

        current_count = ctx.portfolio.position_count
        threshold = int(limit.threshold)

        if current_count >= threshold:
            return RiskCheckResult(
                rule_name="max_positions",
                rule_type=RiskRuleType.SOFT_REDUCTION,
                passed=False,
                reason_code=RiskReasonCode.MAX_POSITIONS,
                detail=f"Open positions {current_count} >= threshold {threshold}",
                reduction_factor=limit.reduction_factor,
            )
        return RiskCheckResult(
            rule_name="max_positions",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_group_concentration(self, ctx: RiskContext) -> RiskCheckResult:
        # Placeholder - requires sector/group mapping
        # For now, always passes
        return RiskCheckResult(
            rule_name="group_concentration",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )

    def _check_correlation_redundancy(self, ctx: RiskContext) -> RiskCheckResult:
        # Placeholder - requires correlation matrix
        # For now, always passes
        return RiskCheckResult(
            rule_name="correlation_redundancy",
            rule_type=RiskRuleType.SOFT_REDUCTION,
            passed=True,
        )


# ============================================================
# POSITION SIZING ENGINE
# ============================================================

class PositionSizer:
    """Deterministic position sizing from risk budget."""

    def __init__(self, constitution: RiskConstitution = CONSTITUTION) -> None:
        self.constitution = constitution

    def compute_budget(self, ctx: RiskContext, checks: tuple[RiskCheckResult, ...]) -> RiskBudget:
        """Compute risk budget from context and check results."""
        from app.risk.models import RiskBudget

        equity = ctx.equity
        if equity <= 0:
            return self._zero_budget(RiskReasonCode.CALCULATION_FAILURE)

        # Base risk budget
        base_budget = equity * self.constitution.BASE_RISK_PER_TRADE

        # Apply soft reductions (multiplicative)
        confidence_red: Decimal = Decimal("1.0")
        volatility_red: Decimal = Decimal("1.0")
        liquidity_red: Decimal = Decimal("1.0")
        concentration_red: Decimal = Decimal("1.0")
        exposure_red: Decimal = Decimal("1.0")
        correlation_red: Decimal = Decimal("1.0")

        limiting_rule: RiskReasonCode | None = None

        for check in checks:
            if check.is_soft_reduction and check.reduction_factor is not None:
                if check.reason_code == RiskReasonCode.CONFIDENCE_REDUCTION:
                    confidence_red = check.reduction_factor
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code == RiskReasonCode.VOLATILITY_REDUCTION:
                    volatility_red = check.reduction_factor
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code == RiskReasonCode.LIQUIDITY_REDUCTION:
                    liquidity_red = check.reduction_factor
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code == RiskReasonCode.SYMBOL_CONCENTRATION:
                    concentration_red = check.reduction_factor
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code in (RiskReasonCode.GROSS_EXPOSURE, RiskReasonCode.NET_EXPOSURE):
                    exposure_red = min(exposure_red, check.reduction_factor)
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code == RiskReasonCode.CORRELATION_REDUNDANCY:
                    correlation_red = check.reduction_factor
                    if limiting_rule is None:
                        limiting_rule = check.reason_code
                elif check.reason_code == RiskReasonCode.MAX_POSITIONS:
                    exposure_red = min(exposure_red, check.reduction_factor)
                    if limiting_rule is None:
                        limiting_rule = check.reason_code

        total_reduction = (
            confidence_red * volatility_red * liquidity_red *
            concentration_red * exposure_red * correlation_red
        )
        adjusted_budget = base_budget * total_reduction

        # ATR-based stop distance
        atr_stop = None
        if ctx.atr_14 is not None and ctx.atr_14 > 0:
            atr_stop = ctx.atr_14 * self.constitution.ATR_STOP_MULTIPLIER
            # Clamp to min/max percentage of price
            min_stop = ctx.reference_price * self.constitution.MIN_STOP_DISTANCE_PCT
            max_stop = ctx.reference_price * self.constitution.MAX_STOP_DISTANCE_PCT
            atr_stop = max(min_stop, min(atr_stop, max_stop))

        # Max position notional
        max_notional = equity * self.constitution.MAX_POSITION_NOTIONAL_PCT

        # Position size from risk budget
        # risk_budget = position_notional * stop_distance_pct
        # position_notional = risk_budget / stop_distance_pct
        if atr_stop is not None and atr_stop > 0:
            stop_distance_pct = atr_stop / ctx.reference_price
            position_notional = adjusted_budget / stop_distance_pct
        else:
            # Fallback: use min stop distance
            stop_distance_pct = self.constitution.MIN_STOP_DISTANCE_PCT
            position_notional = adjusted_budget / stop_distance_pct

        # Cap at max position notional
        position_notional = min(position_notional, max_notional)

        # Convert to shares
        shares = int(position_notional / ctx.reference_price) if ctx.reference_price > 0 else 0
        shares = max(shares, 0)

        # If shares is 0, budget is effectively 0
        if shares == 0:
            adjusted_budget = Decimal("0")
            position_notional = Decimal("0")

        return RiskBudget(
            base_risk_budget=base_budget,
            confidence_reduction=confidence_red,
            volatility_reduction=volatility_red,
            liquidity_reduction=liquidity_red,
            concentration_reduction=concentration_red,
            exposure_reduction=exposure_red,
            correlation_reduction=correlation_red,
            adjusted_risk_budget=adjusted_budget,
            atr_stop_distance=atr_stop,
            max_position_notional=max_notional,
            shares=shares,
            limiting_rule=limiting_rule,
        )

    def _zero_budget(self, limiting_rule: RiskReasonCode) -> RiskBudget:
        from app.risk.models import RiskBudget
        return RiskBudget(
            base_risk_budget=Decimal("0"),
            adjusted_risk_budget=Decimal("0"),
            max_position_notional=Decimal("0"),
            shares=0,
            limiting_rule=limiting_rule,
        )


# ============================================================
# DECISION ENGINE
# ============================================================

class RiskDecisionEngine:
    """Final risk decision from checks and budget."""

    def __init__(self) -> None:
        pass

    def decide(
        self,
        ctx: RiskContext,
        checks: tuple[RiskCheckResult, ...],
        budget: RiskBudget,
    ) -> RiskEvaluation:
        from app.risk.models import RiskDecisionType, RiskEvaluation

        start_time = datetime.now(UTC)

        # Hard rejection check
        hard_rejections = [c for c in checks if c.is_hard_rejection]
        if hard_rejections:
            primary = hard_rejections[0]
            return RiskEvaluation(
                symbol=ctx.trade_thesis.symbol,
                decision=RiskDecisionType.REJECTED,
                reason_code=primary.reason_code or RiskReasonCode.CALCULATION_FAILURE,
                checks=checks,
                risk_budget=None,  # REJECTED => no usable budget
                constitution_version=CONSTITUTION.VERSION,
                evaluated_at=datetime.now(UTC),
                runtime_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
            )

        # Zero budget => REJECTED (not REDUCED)
        if budget.adjusted_risk_budget <= 0 or budget.shares == 0:
            return RiskEvaluation(
                symbol=ctx.trade_thesis.symbol,
                decision=RiskDecisionType.REJECTED,
                reason_code=RiskReasonCode.CALCULATION_FAILURE,
                checks=checks,
                risk_budget=budget,
                constitution_version=CONSTITUTION.VERSION,
                evaluated_at=datetime.now(UTC),
                runtime_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
            )

        # Soft reductions present?
        soft_reductions = [c for c in checks if c.is_soft_reduction]
        if soft_reductions:
            primary = soft_reductions[0]
            return RiskEvaluation(
                symbol=ctx.trade_thesis.symbol,
                decision=RiskDecisionType.REDUCED,
                reason_code=primary.reason_code or RiskReasonCode.WITHIN_LIMITS,
                checks=checks,
                risk_budget=budget,
                constitution_version=CONSTITUTION.VERSION,
                evaluated_at=datetime.now(UTC),
                runtime_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
            )

        # All passed
        return RiskEvaluation(
            symbol=ctx.trade_thesis.symbol,
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            checks=checks,
            risk_budget=budget,
            constitution_version=CONSTITUTION.VERSION,
            evaluated_at=datetime.now(UTC),
            runtime_ms=int((datetime.now(UTC) - start_time).total_seconds() * 1000),
        )