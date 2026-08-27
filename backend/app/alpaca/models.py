"""Stable AlphaCouncil read models decoupled from Alpaca SDK response types."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    currency: str | None = None
    buying_power: str | None = None
    portfolio_value: str | None = None


class MarketClock(BaseModel):
    model_config = ConfigDict(frozen=True)

    is_open: bool
    timestamp: str | None = None
    next_open: str | None = None
    next_close: str | None = None


class AssetInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str | None = None
    tradable: bool
    status: str | None = None
    asset_class: str | None = None
    exchange: str | None = None


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: str
    side: str | None = None


class OrderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    client_order_id: str | None = None
    symbol: str | None = None
    qty: str | None = None
    side: str | None = None
    status: str | None = None
