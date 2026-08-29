"""Exit planner for M7 - builds exit execution plans."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from app.core.config import Settings
from app.market.gateway import MarketDataGateway
from app.market.models import QuoteSnapshot
from app.positions.metrics import ExitRulesEngine
from app.positions.models import (
    ExitDecision,
    ExitDecisionType,
    ExitPlan,
    ManagedPosition,
)
from app.positions.reconciliation import PositionReconciler
from app.risk.models import RiskState

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway
    from app.positions.store import PositionStore


class ExitPlanner:
    """Builds exit execution plans from exit decisions."""

    def __init__(
        self,
        settings: Settings,
        market_gateway: MarketDataGateway,
        alpaca_gateway: AlpacaGateway | None = None,
        position_store: PositionStore | None = None,
        reconciler: PositionReconciler | None = None,
    ) -> None:
        self._settings = settings
        self._market = market_gateway
        self._alpaca = alpaca_gateway
        self._store = position_store
        self._reconciler = reconciler or PositionReconciler(alpaca_gateway, position_store) if alpaca_gateway else None
        self._exit_rules = ExitRulesEngine()

    def build_exit_plan(
        self,
        decision: ExitDecision,
        position: ManagedPosition,
        risk_state: RiskState | None = None,
    ) -> ExitPlan:
        """Build exit execution plan from decision."""
        # Get fresh market data for the symbol
        quote = self._market.get_latest_quote(position.symbol)
        asset = self._get_asset_info(position.symbol) if self._alpaca else None

        # Validate market hours
        if self._alpaca:
            clock = self._alpaca.get_clock()
            if not clock.is_open:
                # Market closed - still create plan but mark as not executable
                pass

        # Calculate exit side and order type
        exit_side = self._determine_exit_side(position)
        position_intent = self._determine_position_intent(position)

        # Determine limit price for exit
        limit_price = self._calculate_exit_limit_price(decision, quote, position)

        # Determine quantity
        quantity = decision.target_quantity_to_close

        # Validate quantity against provider (if reconciler available)
        if self._reconciler and self._store:
            recon_result = self._reconciler.reconcile_position(position.position_id)
            if recon_result and recon_result.provider_quantity < quantity:
                # Clamp to provider quantity to prevent reverse position
                quantity = min(quantity, recon_result.provider_quantity)
                if quantity <= 0:
                    # Nothing to exit
                    pass

        # Create exit plan
        now = datetime.now(UTC)
        ttl_seconds = self._settings.execution_plan_ttl_seconds
        expires_at = now + timedelta(seconds=ttl_seconds)

        return ExitPlan(
            position_id=position.position_id,
            symbol=position.symbol,
            instrument_type=position.instrument_type,
            decision=decision.decision,
            side=exit_side,
            quantity=quantity,
            reason_codes=decision.reason_codes,
            urgency=decision.urgency,
            fresh_bid=quote.bid_price,
            fresh_ask=quote.ask_price,
            fresh_mid=quote.midpoint,
            reference_price=decision.reference_price,
            limit_price=limit_price,
            expected_notional=limit_price * quantity if limit_price else Decimal("0"),
            risk_state_reference=position.constitution_version if risk_state else None,
            constitution_version=position.constitution_version,
            created_at=now,
            expires_at=expires_at,
        )

    def _determine_exit_side(self, position: ManagedPosition) -> Literal["SELL", "BUY_TO_COVER", "SELL_TO_CLOSE"]:
        """Determine the exit order side for the position."""
        if position.instrument_type == "OPTION":
            # Long options only: SELL_TO_CLOSE
            return "SELL_TO_CLOSE"
        if position.side == "LONG":
            return "SELL"
        else:
            return "BUY_TO_COVER"

    def _determine_position_intent(self, position: ManagedPosition) -> Literal["SELL_TO_CLOSE", "BUY_TO_CLOSE"]:
        """Determine position intent for Alpaca API."""
        if position.instrument_type == "OPTION":
            return "SELL_TO_CLOSE"
        if position.side == "LONG":
            return "SELL_TO_CLOSE"
        else:
            return "BUY_TO_CLOSE"

    def _calculate_exit_limit_price(
        self,
        decision: ExitDecision,
        quote: QuoteSnapshot,
        position: ManagedPosition,
    ) -> Decimal:
        """Calculate deterministic exit limit price with bounded aggressiveness."""
        bid = quote.bid_price
        ask = quote.ask_price
        mid = quote.midpoint

        if decision.decision == ExitDecisionType.EXIT and decision.urgency in ("IMMEDIATE", "HIGH"):
            # For urgent exits, be more aggressive
            if position.side == "LONG":
                # Sell at bid for immediate exit
                limit = bid
            else:
                # Buy to cover at ask for immediate exit
                limit = ask
        else:
            # Normal exits: use midpoint
            limit = mid

        # Round to tick size
        return self._round_to_tick(limit)

    def _round_to_tick(self, price: Decimal) -> Decimal:
        """Round price to acceptable tick size."""
        if price >= Decimal("1.00"):
            return price.quantize(Decimal("0.01"))
        return price.quantize(Decimal("0.0001"))

    def _get_asset_info(self, symbol: str) -> object:
        """Get asset info from Alpaca."""
        if self._alpaca:
            return self._alpaca.get_asset(symbol)
        from app.alpaca.models import AssetInfo
        return AssetInfo(
            symbol=symbol,
            name=None,
            tradable=True,
            status="active",
            asset_class="us_equity",
            exchange="NASDAQ",
        )


def create_exit_planner(
    settings: Settings | None = None,
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
    position_store: PositionStore | None = None,
    reconciler: PositionReconciler | None = None,
) -> ExitPlanner:
    """Factory function to create exit planner."""
    if settings is None:
        settings = Settings()
    if market_gateway is None:
        from app.market import AlpacaMarketDataGateway
        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    return ExitPlanner(settings, market_gateway, alpaca_gateway, position_store, reconciler)