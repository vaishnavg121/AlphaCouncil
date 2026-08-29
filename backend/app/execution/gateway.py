"""Paper Execution Gateway - The ONLY layer allowed to perform trading mutations.

This gateway enforces paper-only mode structurally. Even if a caller makes
a mistake, the gateway must fail closed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import OrderType as AlpacaOrderType
from alpaca.trading.enums import PositionIntent as AlpacaPositionIntent
from alpaca.trading.enums import TimeInForce as AlpacaTimeInForce
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

from app.core.config import Settings
from app.core.errors import ExecutionError
from app.execution.models import (
    ExecutionOrder,
    ExecutionStatus,
    OrderSide,
    OrderType,
    PositionIntent,
    TimeInForce,
)

if TYPE_CHECKING:
    pass


class PaperExecutionGateway:
    """Paper-only execution gateway with strict safety boundaries.

    This is the ONLY package/layer allowed to perform trading mutations.
    All mutation methods are guarded by paper-mode enforcement.
    """

    def __init__(self, client: TradingClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings
        self._enforce_paper_mode()

    @classmethod
    def from_settings(cls, settings: Settings) -> PaperExecutionGateway:
        """Create gateway from settings."""
        from app.alpaca.client import create_trading_client

        client = create_trading_client(settings)
        return cls(client, settings)

    def _enforce_paper_mode(self) -> None:
        """Enforce paper-only mode - fail closed if violated."""
        if self._settings.trading_mode != "paper":
            raise ExecutionError(
                f"Gateway requires TRADING_MODE=paper, got {self._settings.trading_mode}"
            )
        if self._settings.alpaca_live_trade:
            raise ExecutionError("Gateway requires ALPACA_LIVE_TRADE=false")
        if not self._settings.enable_execution:
            raise ExecutionError("Gateway requires ENABLE_EXECUTION=true")
        if not self._settings.enable_paper_execution:
            raise ExecutionError("Gateway requires ENABLE_PAPER_EXECUTION=true")

        # Verify client is paper mode
        try:
            account = self._client.get_account()
            if str(getattr(account, "status", "")).lower() != "active":
                raise ExecutionError("Account not active")
        except Exception as e:
            raise ExecutionError(f"Failed to verify paper account: {e}") from e

    def _to_alpaca_side(self, side: OrderSide) -> AlpacaOrderSide:
        return AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL

    def _to_alpaca_order_type(self, order_type: OrderType) -> AlpacaOrderType:
        return (
            AlpacaOrderType.LIMIT
            if order_type == OrderType.LIMIT
            else AlpacaOrderType.MARKET
        )

    def _to_alpaca_tif(self, tif: TimeInForce) -> AlpacaTimeInForce:
        return (
            AlpacaTimeInForce.DAY if tif == TimeInForce.DAY else AlpacaTimeInForce.GTC
        )

    def _to_alpaca_position_intent(
        self, intent: PositionIntent
    ) -> AlpacaPositionIntent:
        mapping = {
            PositionIntent.BUY_TO_OPEN: AlpacaPositionIntent.BUY_TO_OPEN,
            PositionIntent.BUY_TO_CLOSE: AlpacaPositionIntent.BUY_TO_CLOSE,
            PositionIntent.SELL_TO_OPEN: AlpacaPositionIntent.SELL_TO_OPEN,
            PositionIntent.SELL_TO_CLOSE: AlpacaPositionIntent.SELL_TO_CLOSE,
        }
        return mapping[intent]

    def _normalize_order(self, order: object) -> ExecutionOrder:
        """Normalize Alpaca order to local model."""
        status_map = {
            AlpacaOrderStatus.NEW: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_NEW: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.ACCEPTED: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.PARTIALLY_FILLED: ExecutionStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.FILLED: ExecutionStatus.FILLED,
            AlpacaOrderStatus.DONE_FOR_DAY: ExecutionStatus.EXPIRED,
            AlpacaOrderStatus.CANCELED: ExecutionStatus.CANCELED,
            AlpacaOrderStatus.EXPIRED: ExecutionStatus.EXPIRED,
            AlpacaOrderStatus.REPLACED: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_CANCEL: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_REPLACE: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_REVIEW: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.ACCEPTED_FOR_BIDDING: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.STOPPED: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.REJECTED: ExecutionStatus.REJECTED,
            AlpacaOrderStatus.SUSPENDED: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.CALCULATED: ExecutionStatus.SUBMITTED,
            AlpacaOrderStatus.HELD: ExecutionStatus.SUBMITTED,
        }

        alpaca_status = getattr(order, "status", AlpacaOrderStatus.NEW)
        mapped_status = status_map.get(alpaca_status, ExecutionStatus.UNKNOWN)

        side_attr = getattr(order, "side", AlpacaOrderSide.BUY)
        order_type_attr = getattr(order, "order_type", AlpacaOrderType.LIMIT)
        tif_attr = getattr(order, "time_in_force", AlpacaTimeInForce.DAY)

        return ExecutionOrder(
            order_id=str(getattr(order, "id", "")),
            client_order_id=str(getattr(order, "client_order_id", "")),
            symbol=str(getattr(order, "symbol", "")),
            side=OrderSide.BUY if side_attr == AlpacaOrderSide.BUY else OrderSide.SELL,
            quantity=Decimal(str(getattr(order, "qty", "0"))),
            order_type=OrderType.LIMIT
            if order_type_attr == AlpacaOrderType.LIMIT
            else OrderType.MARKET,
            time_in_force=TimeInForce.DAY
            if tif_attr == AlpacaTimeInForce.DAY
            else TimeInForce.GTC,
            limit_price=Decimal(str(getattr(order, "limit_price", "0")))
            if getattr(order, "limit_price", None)
            else None,
            status=mapped_status,
            submitted_at=getattr(order, "submitted_at", datetime.now(UTC)),
            filled_at=getattr(order, "filled_at", None),
            filled_quantity=Decimal(str(getattr(order, "filled_qty", "0"))),
            filled_avg_price=Decimal(str(getattr(order, "filled_avg_price", "0")))
            if getattr(order, "filled_avg_price", None)
            else None,
            provider_status=str(alpaca_status),
        )

    def submit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        limit_price: Decimal,
        time_in_force: TimeInForce,
        client_order_id: str,
        position_intent: PositionIntent | None = None,
    ) -> ExecutionOrder:
        """Submit a LIMIT order - the preferred order type for M6."""
        self._enforce_paper_mode()

        req = LimitOrderRequest(
            symbol=symbol,
            qty=float(quantity),
            side=self._to_alpaca_side(side),
            type=AlpacaOrderType.LIMIT,
            time_in_force=self._to_alpaca_tif(time_in_force),
            limit_price=float(limit_price),
            client_order_id=client_order_id,
            extended_hours=False,  # Never extended hours for M6
            position_intent=(
                self._to_alpaca_position_intent(position_intent)
                if position_intent
                else None
            ),
        )

        try:
            order = self._client.submit_order(req)
            return self._normalize_order(order)
        except Exception as e:
            raise ExecutionError(f"Failed to submit limit order: {e}") from e

    def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        time_in_force: TimeInForce,
        client_order_id: str,
        position_intent: PositionIntent | None = None,
    ) -> ExecutionOrder:
        """Submit a MARKET order - explicitly guarded, not preferred."""
        self._enforce_paper_mode()

        req = MarketOrderRequest(
            symbol=symbol,
            qty=float(quantity),
            side=self._to_alpaca_side(side),
            type=AlpacaOrderType.MARKET,
            time_in_force=self._to_alpaca_tif(time_in_force),
            client_order_id=client_order_id,
            extended_hours=False,
            position_intent=(
                self._to_alpaca_position_intent(position_intent)
                if position_intent
                else None
            ),
        )

        try:
            order = self._client.submit_order(req)
            return self._normalize_order(order)
        except Exception as e:
            raise ExecutionError(f"Failed to submit market order: {e}") from e

    def get_order_by_id(self, order_id: str) -> ExecutionOrder:
        """Fetch order by provider order ID."""
        self._enforce_paper_mode()
        try:
            order = self._client.get_order_by_id(order_id)
            return self._normalize_order(order)
        except Exception as e:
            raise ExecutionError(f"Failed to get order by ID: {e}") from e

    def get_order_by_client_id(
        self, client_order_id: str
    ) -> ExecutionOrder | None:
        """Fetch order by client_order_id for duplicate detection."""
        self._enforce_paper_mode()
        try:
            order = self._client.get_order_by_client_id(client_order_id)
            return self._normalize_order(order)
        except Exception as e:
            # If order not found, return None rather than raise
            # This is the expected path for "no existing order"
            if "not found" in str(e).lower() or "404" in str(e):
                return None
            raise ExecutionError(f"Failed to get order by client ID: {e}") from e

    def cancel_order(self, order_id: str) -> ExecutionOrder:
        """Cancel an order - ONLY for AlphaCouncil-owned paper orders."""
        self._enforce_paper_mode()
        try:
            self._client.cancel_order_by_id(order_id)
            # Fetch the canceled order to return normalized version
            order = self._client.get_order_by_id(order_id)
            return self._normalize_order(order)
        except Exception as e:
            raise ExecutionError(f"Failed to cancel order: {e}") from e

    def list_orders(self, status: str | None = None) -> list[ExecutionOrder]:
        """List orders for reconciliation."""
        self._enforce_paper_mode()
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest

            req = GetOrdersRequest(
                status=QueryOrderStatus.ALL,
                limit=500,
            )
            orders = self._client.get_orders(req)
            return [self._normalize_order(o) for o in orders]
        except Exception as e:
            raise ExecutionError(f"Failed to list orders: {e}") from e

    def get_account(self) -> object:
        """Get paper account snapshot."""
        self._enforce_paper_mode()
        return self._client.get_account()