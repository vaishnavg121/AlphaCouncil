from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.alpaca.auth import AlpacaAuthType, AlpacaCredentialsProvider
from app.core.config import Settings


def settings_without_dotenv(**overrides: Any) -> Settings:
    return Settings.model_construct(**overrides)


def write_profile(root: Path, config: str, profile: str | None = None) -> None:
    root.mkdir()
    (root / "config.yaml").write_text(config, encoding="utf-8")
    if profile is not None:
        profiles = root / "profiles"
        profiles.mkdir()
        (profiles / "paper.yaml").write_text(profile, encoding="utf-8")


def test_complete_environment_api_key_bundle_has_precedence(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "access_token: profile-token\n")
    settings = settings_without_dotenv(
        alpaca_api_key=SecretStr("environment-key"),
        alpaca_secret_key=SecretStr("environment-secret"),
    )
    credentials = AlpacaCredentialsProvider(settings, (root,)).resolve()
    assert credentials.auth_type is AlpacaAuthType.API_KEYS
    assert credentials.source == "environment"


def test_partial_environment_bundle_never_merges_with_profile(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "access_token: profile-token\n")
    settings = settings_without_dotenv(alpaca_api_key=SecretStr("environment-key"))
    credentials = AlpacaCredentialsProvider(settings, (root,)).resolve()
    assert credentials.auth_type is AlpacaAuthType.OAUTH_PROFILE
    assert credentials.oauth_token is not None
    assert credentials.oauth_token.get_secret_value() == "profile-token"


def test_active_paper_oauth_profile_resolves(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "auth:\n  access_token: profile-token\n")
    credentials = AlpacaCredentialsProvider(settings_without_dotenv(), (root,)).resolve()
    assert credentials.auth_type is AlpacaAuthType.OAUTH_PROFILE
    assert credentials.source == "active_cli_profile"


def test_nested_camel_case_active_profile_and_token_resolve(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(
        root,
        "activeProfile:\n  name: paper\n",
        "auth:\n  accessToken: profile-token\n",
    )
    credentials = AlpacaCredentialsProvider(settings_without_dotenv(), (root,)).resolve()
    assert credentials.auth_type is AlpacaAuthType.OAUTH_PROFILE


def test_active_paper_profile_api_bundle_resolves_atomically(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "api_key: key\napi_secret: secret\n")
    credentials = AlpacaCredentialsProvider(settings_without_dotenv(), (root,)).resolve()
    assert credentials.auth_type is AlpacaAuthType.API_KEYS
    assert credentials.api_key is not None
    assert credentials.secret_key is not None


def test_malformed_or_missing_profile_is_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "access_token: [bad\n")
    malformed = AlpacaCredentialsProvider(settings_without_dotenv(), (root,)).resolve()
    missing_provider = AlpacaCredentialsProvider(settings_without_dotenv(), (tmp_path / "missing",))
    missing = missing_provider.resolve()
    assert malformed.available is False
    assert missing.available is False


def test_credential_representation_does_not_expose_profile_token(tmp_path: Path) -> None:
    root = tmp_path / "alpaca"
    write_profile(root, "active_profile: paper\n", "access_token: profile-token-do-not-leak\n")
    credentials = AlpacaCredentialsProvider(settings_without_dotenv(), (root,)).resolve()
    assert "profile-token-do-not-leak" not in repr(credentials)
