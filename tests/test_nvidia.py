from __future__ import annotations

from typing import Any

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.core.health import HealthStatus
from app.llm.nvidia import NvidiaLLMProvider


def settings_without_dotenv(**overrides: Any) -> Settings:
    return Settings.model_construct(**overrides)


def test_nvidia_missing_key_is_blocked() -> None:
    health = NvidiaLLMProvider(settings_without_dotenv(llm_model="test-model")).healthcheck()
    assert health.status is HealthStatus.BLOCKED
    assert "NVIDIA_API_KEY" in (health.message or "")


def test_nvidia_timeout_is_secret_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    health = NvidiaLLMProvider(
        settings_without_dotenv(nvidia_api_key=SecretStr("secret-value"), llm_model="test-model"),
        client=client,
    ).healthcheck()
    assert health.status is HealthStatus.FAIL
    assert "secret-value" not in repr(health)


def test_nvidia_provider_error_is_handled() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401)))
    health = NvidiaLLMProvider(
        settings_without_dotenv(nvidia_api_key=SecretStr("secret-value"), llm_model="test-model"),
        client=client,
    ).healthcheck()
    assert health.status is HealthStatus.FAIL


def test_nvidia_success_requires_exact_ok() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
        )
    )
    health = NvidiaLLMProvider(
        settings_without_dotenv(nvidia_api_key=SecretStr("secret-value"), llm_model="test-model"),
        client=client,
    ).healthcheck()
    assert health.status is HealthStatus.PASS
    assert "secret-value" not in health.model_dump_json()
