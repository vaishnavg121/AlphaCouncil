"""Fail-closed configuration for the PRE-M0 foundation.

This module deliberately contains no broker client construction or network activity.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with a paper-only, execution-disabled default posture."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_env: str = "development"
    trading_mode: Literal["paper"] = "paper"
    enable_execution: bool = False

    alpaca_api_key: SecretStr | None = None
    alpaca_secret_key: SecretStr | None = None
    alpaca_live_trade: bool = False

    llm_provider: str = "nvidia"
    llm_model: str | None = None
    nvidia_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def reject_live_trading(self) -> Settings:
        """Refuse any configuration that could authorize a live Alpaca connection."""
        if self.alpaca_live_trade:
            raise ValueError("ALPACA_LIVE_TRADE=true is prohibited by AlphaCouncil safety policy")
        if self.trading_mode != "paper":
            raise ValueError("TRADING_MODE must be paper during development")
        return self

    @property
    def alpaca_credentials_configured(self) -> bool:
        """Whether both backend-only Alpaca credentials are present, without exposing them."""
        return self.alpaca_api_key is not None and self.alpaca_secret_key is not None

    @property
    def nvidia_credentials_configured(self) -> bool:
        """Whether the NVIDIA credential is present, without exposing it."""
        return self.nvidia_api_key is not None


def get_settings() -> Settings:
    """Load settings on demand so imports cannot cause configuration or broker side effects."""
    return Settings()
