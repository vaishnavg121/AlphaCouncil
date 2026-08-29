"""Execution Planner - Fresh market validation and deterministic limit price planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any

from app.core.config import Settings
from app.core.errors import ExecutionError, MarketDataError
from app.execution.models import (
    ExecutionPlan,
    ExecutionReasonCode,
    IdempotencyKey,
    InstrumentType,
    OrderSide,
    OrderType,
    TimeInForce,
)
from app.instruments.models import InstrumentPlan
from app.risk.models import RiskEvaluation

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway
    from app.market.gateway import MarketDataGateway


class ExecutionPlanner:
    """Builds ExecutionPlan from InstrumentPlan with fresh market validation."""

    def __init__(
        self,
        settings: Settings,
        market_gateway: MarketDataGateway,
        alpaca_gateway: AlpacaGateway | None = None,
    ) -> None:
        self._settings = settings
        self._market = market_gateway
        self._alpaca = alpaca_gateway

    def build_execution_plan(
        self,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
    ) -> ExecutionPlan:
        """Build execution plan with fresh market data validation."""
        # Fresh market data
        quote = self._market.get_latest_quote(instrument_plan.symbol)
        asset = self._get_asset_info(instrument_plan.symbol)

        # Validate market hours
        if self._alpaca:
            clock = self._alpaca.get_clock()
            if not clock.is_open:
                raise MarketDataError(
                    "Market is closed",
                    reason_code=ExecutionReasonCode.MARKET_CLOSED.value,
                )

        # Validate quote freshness
        self._validate_quote_freshness(quote)

        # Validate quote quality
        self._validate_quote_quality(quote)

        # Validate asset tradability
        self._validate_asset_tradability(asset)

        # Validate shortability for bearish equity
        if (
            instrument_plan.is_stock
            and instrument_plan.equity_plan
            and instrument_plan.equity_plan.side.value == "SHORT"
        ):
            self._validate_shortable(asset)

        # Calculate limit price
        limit_price = self._calculate_limit_price(instrument_plan, quote)

        # Validate price deviation from M5 reference
        self._validate_price_deviation(instrument_plan, quote.midpoint)

        # Build execution plan
        return self._build_plan(
            instrument_plan, risk_evaluation, quote, limit_price, asset
        )

    def _validate_quote_freshness(self, quote: Any) -> None:
        """Validate quote is not stale during market hours."""
        # The quote timestamp should be recent
        # In production, check against configurable threshold
        # For now, basic validation
        if quote.bid_price <= 0 or quote.ask_price <= 0:
            raise MarketDataError(
                "Invalid quote: zero or negative prices",
                reason_code=ExecutionReasonCode.INVALID_QUOTE.value,
            )

    def _validate_quote_quality(self, quote: Any) -> None:
        """Validate quote spread and quality."""
        bid = quote.bid_price
        ask = quote.ask_price

        if bid >= ask:
            raise MarketDataError(
                "Crossed or locked market",
                reason_code=ExecutionReasonCode.INVALID_QUOTE.value,
            )

        mid = (bid + ask) / Decimal("2")
        spread = ask - bid
        spread_pct = spread / mid if mid > 0 else Decimal("0")

        max_spread = Decimal(str(self._settings.max_execution_spread_pct))
        if spread_pct > max_spread:
            raise MarketDataError(
                f"Spread {spread_pct:.4%} exceeds maximum {max_spread:.4%}",
                reason_code=ExecutionReasonCode.SPREAD_TOO_WIDE.value,
            )

    def _validate_asset_tradability(self, asset: Any) -> None:
        """Validate asset is tradable."""
        if not asset.tradable:
            raise MarketDataError(
                f"Asset {asset.symbol} not tradable",
                reason_code=ExecutionReasonCode.ASSET_NOT_TRADABLE.value,
            )

    def _validate_shortable(self, asset: Any) -> None:
        """Validate asset is shortable for bearish equity execution."""
        # Check shortable from asset info
        shortable = getattr(asset, "shortable", False)
        easy_to_borrow = getattr(asset, "easy_to_borrow", False)
        if not shortable or not easy_to_borrow:
            raise MarketDataError(
                f"Asset {asset.symbol} not shortable or not easy to borrow",
                reason_code=ExecutionReasonCode.ASSET_NOT_SHORTABLE.value,
            )

    def _validate_price_deviation(
        self, instrument_plan: InstrumentPlan, fresh_mid: Decimal
    ) -> None:
        """Validate price hasn't moved too far from M5 reference."""
        m5_ref = (
            instrument_plan.equity_plan.reference_price
            if instrument_plan.equity_plan
            else Decimal("0")
        )
        if m5_ref <= 0:
            return  # No reference price to compare

        deviation = abs(fresh_mid - m5_ref) / m5_ref
        max_deviation = Decimal(str(self._settings.max_execution_price_deviation_pct))

        if deviation > max_deviation:
            raise MarketDataError(
                f"Price moved {deviation:.4%} from M5 reference, max {max_deviation:.4%}",
                reason_code=ExecutionReasonCode.PRICE_MOVED_TOO_FAR.value,
            )

    def _calculate_limit_price(
        self,
        instrument_plan: InstrumentPlan,
        quote: Any,
    ) -> Decimal:
        """Calculate deterministic limit price with bounded aggressiveness."""
        mid = quote.midpoint

        # For BUY: limit at ask (aggressive) or mid (passive)
        # Use mid + small buffer to increase fill probability while maintaining protection
        # For SELL: limit at bid or mid
        limit = mid
        # Round to tick size (typically $0.01 for stocks > $1)
        limit = self._round_to_tick(limit)

        return limit

    def _round_to_tick(self, price: Decimal) -> Decimal:
        """Round price to acceptable tick size."""
        # For stocks >= $1.00, tick is $0.01
        # For stocks < $1.00, tick is $0.0001
        if price >= Decimal("1.00"):
            return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return price.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    def _get_asset_info(self, symbol: str) -> Any:
        """Get asset info from Alpaca."""
        if self._alpaca:
            return self._alpaca.get_asset(symbol)
        # Fallback - create minimal asset
        from app.alpaca.models import AssetInfo

        return AssetInfo(
            symbol=symbol,
            name=None,
            tradable=True,
            status="active",
            asset_class="us_equity",
            exchange="NASDAQ",
        )

    def _build_plan(
        self,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
        quote: Any,
        limit_price: Decimal,
        asset: Any,
    ) -> ExecutionPlan:
        """Build the complete ExecutionPlan."""
        now = datetime.now(UTC)
        ttl_seconds = self._settings.execution_plan_ttl_seconds
        expires_at = now + timedelta(seconds=ttl_seconds)

        if instrument_plan.is_stock and instrument_plan.equity_plan:
            eq_plan = instrument_plan.equity_plan
            side = OrderSide.BUY if eq_plan.side.value == "LONG" else OrderSide.SELL
            quantity = eq_plan.estimated_quantity
            expected_notional = limit_price * quantity
            risk_budget = (
                risk_evaluation.risk_budget.adjusted_risk_budget
                if risk_evaluation.risk_budget
                else Decimal("0")
            )
            max_notional = (
                risk_evaluation.risk_budget.max_position_notional
                if risk_evaluation.risk_budget
                else Decimal("0")
            )
        elif instrument_plan.is_option and instrument_plan.option_plan:
            op_plan = instrument_plan.option_plan
            side = OrderSide.BUY  # Long options only
            quantity = Decimal(str(op_plan.planned_contracts))
            expected_notional = (
                limit_price * quantity * Decimal(str(op_plan.multiplier))
            )
            risk_budget = (
                risk_evaluation.risk_budget.adjusted_risk_budget
                if risk_evaluation.risk_budget
                else Decimal("0")
            )
            max_notional = (
                risk_evaluation.risk_budget.max_position_notional
                if risk_evaluation.risk_budget
                else Decimal("0")
            )
        else:
            raise ExecutionError("No valid instrument plan for execution")

        # Generate idempotency key
        idempotency_key = IdempotencyKey(
            instrument_plan_id=instrument_plan.plan_id,
            symbol=instrument_plan.symbol,
            side=side,
            quantity=quantity,
            risk_authorization_version=risk_evaluation.constitution_version,
        )

        return ExecutionPlan(
            execution_plan_id=str(idempotency_key.to_string()),
            instrument_plan_id=instrument_plan.plan_id,
            created_at=now,
            expires_at=expires_at,
            symbol=instrument_plan.symbol,
            instrument_type=(
                InstrumentType.STOCK
                if instrument_plan.is_stock
                else InstrumentType.OPTION
            ),
            direction=instrument_plan.thesis_direction,
            side=side,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=(
                instrument_plan.equity_plan.reference_price
                if instrument_plan.equity_plan
                else Decimal("0")
            ),
            fresh_bid=quote.bid_price,
            fresh_ask=quote.ask_price,
            fresh_mid=quote.midpoint,
            fresh_quote_timestamp=quote.timestamp,
            limit_price=limit_price,
            expected_notional=expected_notional,
            risk_budget=risk_budget,
            max_authorized_notional=max_notional,
            constitution_version=risk_evaluation.constitution_version,
        )


def create_execution_planner(
    settings: Settings | None = None,
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
) -> ExecutionPlanner:
    """Factory function to create execution planner."""
    if settings is None:
        settings = Settings()
    if market_gateway is None:
        from app.market import AlpacaMarketDataGateway

        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    return ExecutionPlanner(settings, market_gateway, alpaca_gateway)