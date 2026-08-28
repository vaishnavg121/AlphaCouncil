"""Single read-only AlphaCouncil boundary for Alpaca SDK access during M0."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from alpaca.trading.client import TradingClient

from app.alpaca.client import create_trading_client
from app.alpaca.models import (
    AccountSnapshot,
    AssetInfo,
    MarketClock,
    OrderSnapshot,
    PositionSnapshot,
)
from app.core.config import Settings


class AlpacaGateway:
    """Expose only read operations and normalize SDK responses into local contracts."""

    def __init__(self, client: TradingClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> AlpacaGateway:
        return cls(create_trading_client(settings))

    def get_account(self) -> AccountSnapshot:
        account = self._client.get_account()
        return AccountSnapshot(
            status=str(_field(account, "status")),
            currency=_optional_string(account, "currency"),
            buying_power=_optional_string(account, "buying_power"),
            portfolio_value=_optional_string(account, "portfolio_value"),
            equity=_optional_string(account, "equity"),
            cash=_optional_string(account, "cash"),
            initial_margin=_optional_string(account, "initial_margin"),
            maintenance_margin=_optional_string(account, "maintenance_margin"),
            daytrade_count=_field(account, "daytrade_count") if hasattr(account, "daytrade_count") else None,
            account_id=_optional_string(account, "id"),
        )

    def get_clock(self) -> MarketClock:
        clock = self._client.get_clock()
        return MarketClock(
            is_open=bool(_field(clock, "is_open")),
            timestamp=_optional_string(clock, "timestamp"),
            next_open=_optional_string(clock, "next_open"),
            next_close=_optional_string(clock, "next_close"),
        )

    def get_asset(self, symbol: str) -> AssetInfo:
        asset = self._client.get_asset(symbol)
        return AssetInfo(
            symbol=str(_field(asset, "symbol")),
            name=_optional_string(asset, "name"),
            tradable=bool(_field(asset, "tradable")),
            status=_optional_string(asset, "status"),
            asset_class=_optional_string(asset, "asset_class"),
            exchange=_optional_string(asset, "exchange"),
        )

    def list_positions(self) -> list[PositionSnapshot]:
        return [
            PositionSnapshot(
                symbol=str(_field(position, "symbol")),
                qty=str(_field(position, "qty")),
                side=_optional_string(position, "side"),
                market_value=_optional_string(position, "market_value"),
                avg_entry_price=_optional_string(position, "avg_entry_price"),
                unrealized_pl=_optional_string(position, "unrealized_pl"),
            )
            for position in self._client.get_all_positions()
        ]

    def list_orders(self) -> list[OrderSnapshot]:
        return [
            OrderSnapshot(
                client_order_id=_optional_string(order, "client_order_id"),
                symbol=_optional_string(order, "symbol"),
                qty=_optional_string(order, "qty"),
                side=_optional_string(order, "side"),
                status=_optional_string(order, "status"),
            )
            for order in self._client.get_orders()
        ]


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value[name]
    return getattr(value, name)


def _optional_string(value: Any, name: str) -> str | None:
    try:
        item = _field(value, name)
    except (AttributeError, KeyError):
        return None
    return None if item is None else str(item)
