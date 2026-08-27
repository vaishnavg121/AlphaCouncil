from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic import SecretStr

from app.alpaca.auth import AlpacaCredentialsProvider
from app.alpaca.client import create_trading_client
from app.alpaca.gateway import AlpacaGateway
from app.core.config import Settings


def settings_without_dotenv(**overrides: Any) -> Settings:
    return Settings.model_construct(**overrides)


class FakeTradingClient:
    def get_account(self) -> SimpleNamespace:
        return SimpleNamespace(status="ACTIVE", currency="USD", buying_power="400000")

    def get_clock(self) -> SimpleNamespace:
        return SimpleNamespace(is_open=False, timestamp="2026-08-28T00:00:00Z")

    def get_asset(self, symbol: str) -> SimpleNamespace:
        return SimpleNamespace(symbol=symbol, name="Apple Inc.", tradable=True, status="active")

    def get_all_positions(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(symbol="AAPL", qty="2", side="long")]

    def get_orders(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                client_order_id="test", symbol="AAPL", qty="2", side="buy", status="new"
            )
        ]


def test_gateway_normalizes_read_only_responses() -> None:
    gateway = AlpacaGateway(FakeTradingClient())  # type: ignore[arg-type]
    assert gateway.get_account().status == "ACTIVE"
    assert gateway.get_clock().is_open is False
    assert gateway.get_asset("AAPL").tradable is True
    assert gateway.list_positions()[0].symbol == "AAPL"
    assert gateway.list_orders()[0].status == "new"


def test_api_key_client_factory_always_sets_paper_true(monkeypatch: Any) -> None:
    received: dict[str, object] = {}

    def fake_client(**kwargs: object) -> object:
        received.update(kwargs)
        return object()

    monkeypatch.setattr("app.alpaca.client.TradingClient", fake_client)
    settings = settings_without_dotenv(
        alpaca_api_key=SecretStr("key"), alpaca_secret_key=SecretStr("secret")
    )
    client = create_trading_client(settings)
    assert client is not None
    assert received == {"api_key": "key", "secret_key": "secret", "paper": True}


def test_oauth_client_factory_always_sets_paper_true(tmp_path: Any, monkeypatch: Any) -> None:
    root = tmp_path / "alpaca"
    root.mkdir()
    (root / "config.yaml").write_text("active_profile: paper\n", encoding="utf-8")
    profiles = root / "profiles"
    profiles.mkdir()
    (profiles / "paper.yaml").write_text("access_token: token\n", encoding="utf-8")
    received: dict[str, object] = {}

    def fake_client(**kwargs: object) -> object:
        received.update(kwargs)
        return object()

    monkeypatch.setattr("app.alpaca.client.TradingClient", fake_client)
    client = create_trading_client(
        settings_without_dotenv(), AlpacaCredentialsProvider(settings_without_dotenv(), (root,))
    )
    assert client is not None
    assert received == {"oauth_token": "token", "paper": True}
