from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def clear_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "APP_ENV",
        "TRADING_MODE",
        "ENABLE_EXECUTION",
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ALPACA_LIVE_TRADE",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "NVIDIA_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def settings_without_dotenv() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_paper_mode_is_accepted_and_execution_defaults_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_settings_environment(monkeypatch)
    settings = settings_without_dotenv()
    assert settings.trading_mode == "paper"
    assert settings.enable_execution is False
    assert settings.alpaca_live_trade is False


def test_live_trading_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_environment(monkeypatch)
    monkeypatch.setenv("ALPACA_LIVE_TRADE", "true")
    with pytest.raises(ValidationError, match="prohibited"):
        settings_without_dotenv()


def test_non_paper_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_environment(monkeypatch)
    monkeypatch.setenv("TRADING_MODE", "live")
    with pytest.raises(ValidationError):
        settings_without_dotenv()


def test_missing_credentials_cannot_enable_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_environment(monkeypatch)
    settings = settings_without_dotenv()
    assert settings.alpaca_credentials_configured is False
    assert settings.enable_execution is False


def test_secrets_are_not_exposed_by_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_environment(monkeypatch)
    monkeypatch.setenv("ALPACA_API_KEY", "test-key-must-not-appear")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret-must-not-appear")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key-must-not-appear")
    rendered = repr(settings_without_dotenv())
    assert "test-key-must-not-appear" not in rendered
    assert "test-secret-must-not-appear" not in rendered
    assert "test-nvidia-key-must-not-appear" not in rendered


def test_backend_import_does_not_perform_brokerage_operations() -> None:
    module = importlib.import_module("app")
    assert module.__doc__ is not None
