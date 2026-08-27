"""Credential resolution for the Alpaca paper environment.

Resolution order is atomic: a complete environment API-key pair, then the
active paper-safe CLI OAuth profile, then a complete profile API-key pair.
Partial bundles are never combined.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, SecretStr

from app.core.config import Settings
from app.core.errors import CredentialsUnavailableError


class AlpacaAuthType(StrEnum):
    API_KEYS = "API_KEYS"
    OAUTH_PROFILE = "OAUTH_PROFILE"
    UNAVAILABLE = "UNAVAILABLE"


class AlpacaCredentials(BaseModel):
    """A resolved authentication bundle. Secret fields are never represented plainly."""

    model_config = ConfigDict(frozen=True)

    auth_type: AlpacaAuthType
    paper: bool = True
    api_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    oauth_token: SecretStr | None = None
    source: str | None = None

    @property
    def available(self) -> bool:
        return self.auth_type is not AlpacaAuthType.UNAVAILABLE


class AlpacaCredentialsProvider:
    """Resolve a complete credential bundle without writing to CLI configuration."""

    def __init__(self, settings: Settings, config_roots: tuple[Path, ...] | None = None) -> None:
        self._settings = settings
        self._config_roots = config_roots or self._default_config_roots()

    @staticmethod
    def _default_config_roots() -> tuple[Path, ...]:
        roots = [Path.home() / ".config" / "alpaca"]
        app_data = os.getenv("APPDATA")
        if app_data:
            roots.append(Path(app_data) / "alpaca")
        xdg_config = os.getenv("XDG_CONFIG_HOME")
        if xdg_config:
            roots.append(Path(xdg_config) / "alpaca")
        return tuple(dict.fromkeys(roots))

    def resolve(self) -> AlpacaCredentials:
        """Return the highest-precedence complete credential bundle, never a merged one."""
        if self._settings.alpaca_credentials_configured:
            return AlpacaCredentials(
                auth_type=AlpacaAuthType.API_KEYS,
                api_key=self._settings.alpaca_api_key,
                secret_key=self._settings.alpaca_secret_key,
                source="environment",
            )

        for root in self._config_roots:
            resolved = self._resolve_active_profile(root)
            if resolved is not None:
                return resolved

        return AlpacaCredentials(auth_type=AlpacaAuthType.UNAVAILABLE)

    def require(self) -> AlpacaCredentials:
        credentials = self.resolve()
        if not credentials.available:
            raise CredentialsUnavailableError(
                "No complete paper-safe Alpaca credential bundle is available"
            )
        return credentials

    def _resolve_active_profile(self, root: Path) -> AlpacaCredentials | None:
        config = self._read_yaml(root / "config.yaml")
        if not config:
            return None
        active_name = self._active_profile_name(config)
        if active_name is None or Path(active_name).name != active_name:
            return None

        profile = self._read_profile(root, active_name)
        if profile is None or not self._profile_is_paper(active_name, profile):
            return None

        oauth_token = self._find_secret(profile, {"oauth_token", "access_token"})
        if oauth_token is not None:
            return AlpacaCredentials(
                auth_type=AlpacaAuthType.OAUTH_PROFILE,
                oauth_token=SecretStr(oauth_token),
                source="active_cli_profile",
            )

        api_key = self._find_secret(profile, {"api_key", "key_id"})
        secret_key = self._find_secret(profile, {"api_secret", "secret_key"})
        if api_key is not None and secret_key is not None:
            return AlpacaCredentials(
                auth_type=AlpacaAuthType.API_KEYS,
                api_key=SecretStr(api_key),
                secret_key=SecretStr(secret_key),
                source="active_cli_profile",
            )
        return None

    @staticmethod
    def _read_yaml(path: Path) -> Mapping[str, Any] | None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            return None
        return data if isinstance(data, Mapping) else None

    def _read_profile(self, root: Path, active_name: str) -> Mapping[str, Any] | None:
        for extension in (".yaml", ".yml"):
            profile = self._read_yaml(root / "profiles" / f"{active_name}{extension}")
            if profile is not None:
                return profile
        return None

    @staticmethod
    def _active_profile_name(config: Mapping[str, Any]) -> str | None:
        valid_keys = {
            "active_profile",
            "activeprofile",
            "active",
            "profile",
            "current_profile",
            "currentprofile",
            "current",
            "default_profile",
            "defaultprofile",
            "default",
        }
        for key, value in config.items():
            normalized = AlpacaCredentialsProvider._normalize_key(key)
            if normalized not in valid_keys:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, Mapping):
                for nested_key in ("name", "profile"):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
        return None

    @staticmethod
    def _profile_is_paper(active_name: str, profile: Mapping[str, Any]) -> bool:
        if active_name.casefold() == "paper":
            return True
        environment = AlpacaCredentialsProvider._find_secret(profile, {"environment", "env"})
        endpoint = AlpacaCredentialsProvider._find_secret(profile, {"base_url", "trading_url"})
        return environment == "paper" or (
            endpoint is not None and "paper-api.alpaca.markets" in endpoint
        )

    @staticmethod
    def _find_secret(data: Mapping[str, Any], names: set[str]) -> str | None:
        normalized_names = {AlpacaCredentialsProvider._normalize_key(name) for name in names}
        for key, value in data.items():
            normalized = AlpacaCredentialsProvider._normalize_key(key)
            if normalized in normalized_names and isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, Mapping):
                found = AlpacaCredentialsProvider._find_secret(value, names)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _normalize_key(key: object) -> str:
        """Match snake-case, kebab-case, and common camel-case CLI YAML keys."""
        return str(key).casefold().replace("-", "_").replace("_", "")
