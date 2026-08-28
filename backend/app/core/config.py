"""Fail-closed configuration for the AlphaCouncil foundation.

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
    alpaca_data_feed: Literal["iex", "sip", "otc"] = "iex"

    llm_provider: str = "nvidia"
    llm_model: str | None = None
    nvidia_api_key: SecretStr | None = None

    # M2 Discovery Configuration
    discovery_universe_mode: Literal["curated", "alpaca"] = "curated"
    discovery_preliminary_k: int = 20
    discovery_deep_analysis_k: int = 15
    discovery_final_k: int = 10
    discovery_min_price: float = 5.0
    discovery_min_avg_dollar_volume: float = 5_000_000.0
    discovery_min_history_bars: int = 50
    discovery_max_per_group: int = 3
    discovery_deep_concurrency: int = 3

    # Score weights (normalized internally)
    discovery_weight_momentum: float = 0.20
    discovery_weight_trend: float = 0.20
    discovery_weight_volume: float = 0.15
    discovery_weight_volatility: float = 0.15
    discovery_weight_mean_reversion: float = 0.10
    discovery_weight_liquidity: float = 0.10
    discovery_weight_quality: float = 0.10

    # M5 Instrument Selection Configuration
    options_enabled: bool = True
    option_min_dte: int = 7
    option_target_dte_min: int = 21
    option_target_dte_max: int = 60
    option_max_dte: int = 90
    option_min_moneyness_pct: float = 0.85
    option_max_moneyness_pct: float = 1.15
    option_target_abs_delta_min: float = 0.40
    option_target_abs_delta_max: float = 0.75
    option_hard_abs_delta_min: float = 0.25
    option_hard_abs_delta_max: float = 0.90
    option_max_spread_pct: float = 0.10
    option_preferred_spread_pct: float = 0.03
    option_max_contracts_per_plan: int = 10
    option_min_instrument_score: float = 40.0
    option_complexity_margin: float = 5.0
    option_require_greeks: bool = False
    option_require_iv: bool = False

    @model_validator(mode="after")
    def reject_live_trading(self) -> Settings:
        """Refuse any configuration that could authorize a live Alpaca connection."""
        if self.alpaca_live_trade:
            raise ValueError("ALPACA_LIVE_TRADE=true is prohibited by AlphaCouncil safety policy")
        if self.trading_mode != "paper":
            raise ValueError("TRADING_MODE must be paper during development")
        if self.enable_execution:
            raise ValueError("ENABLE_EXECUTION=true is prohibited during M0")
        return self

    @property
    def alpaca_credentials_configured(self) -> bool:
        """Whether both backend-only Alpaca credentials are present, without exposing them."""
        return self.alpaca_api_key is not None and self.alpaca_secret_key is not None

    @property
    def alpaca_environment_credentials_partial(self) -> bool:
        """Whether exactly one API-key environment credential was supplied."""
        return (self.alpaca_api_key is None) != (self.alpaca_secret_key is None)

    @property
    def nvidia_credentials_configured(self) -> bool:
        """Whether the NVIDIA credential is present, without exposing it."""
        return self.nvidia_api_key is not None


def get_settings() -> Settings:
    """Load settings on demand so imports cannot cause configuration or broker side effects."""
    return Settings()
