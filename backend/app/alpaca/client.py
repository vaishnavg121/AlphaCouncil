"""PAPER-only Alpaca client construction."""

from __future__ import annotations

from alpaca.trading.client import TradingClient

from app.alpaca.auth import AlpacaAuthType, AlpacaCredentialsProvider
from app.core.config import Settings
from app.core.errors import CredentialsUnavailableError


def create_trading_client(
    settings: Settings,
    credentials_provider: AlpacaCredentialsProvider | None = None,
) -> TradingClient:
    """Create an Alpaca SDK client that is structurally unable to be live-mode."""
    credentials = (credentials_provider or AlpacaCredentialsProvider(settings)).require()
    if (
        credentials.auth_type is AlpacaAuthType.OAUTH_PROFILE
        and credentials.oauth_token is not None
    ):
        return TradingClient(oauth_token=credentials.oauth_token.get_secret_value(), paper=True)
    if (
        credentials.auth_type is AlpacaAuthType.API_KEYS
        and credentials.api_key is not None
        and credentials.secret_key is not None
    ):
        return TradingClient(
            api_key=credentials.api_key.get_secret_value(),
            secret_key=credentials.secret_key.get_secret_value(),
            paper=True,
        )
    raise CredentialsUnavailableError(
        "No complete paper-safe Alpaca credential bundle is available"
    )
