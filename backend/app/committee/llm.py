"""NVIDIA LLM provider for M3 committee with structured output support."""

from __future__ import annotations

from time import perf_counter

import httpx

from app.core.config import Settings
from app.core.health import HealthStatus, ServiceHealth

NVIDIA_API_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NvidiaCommitteeLLMProvider:
    """NVIDIA LLM provider for committee with structured output support."""

    def __init__(
        self,
        settings: Settings,
        *,
        timeout_seconds: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._timeout_seconds = timeout_seconds
        self._client = client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        """Complete a chat request with the NVIDIA LLM."""
        if not self._settings.nvidia_credentials_configured:
            raise RuntimeError("NVIDIA_API_KEY is not configured")
        if not self._settings.llm_model:
            raise RuntimeError("LLM_MODEL is not configured")

        assert self._settings.nvidia_api_key is not None
        api_key = self._settings.nvidia_api_key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if self._client is not None:
            response = self._client.post(
                f"{NVIDIA_API_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self._timeout_seconds,
            )
        else:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                response = client.post(
                    f"{NVIDIA_API_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )

        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()

    def healthcheck(self) -> ServiceHealth:
        """Perform health check."""
        if not self._settings.nvidia_credentials_configured:
            return ServiceHealth(
                service="nvidia_llm_committee",
                status=HealthStatus.BLOCKED,
                endpoint=NVIDIA_API_BASE_URL,
                message="NVIDIA_API_KEY is not configured",
            )
        if not self._settings.llm_model:
            return ServiceHealth(
                service="nvidia_llm_committee",
                status=HealthStatus.BLOCKED,
                endpoint=NVIDIA_API_BASE_URL,
                message="LLM_MODEL is not configured",
            )

        assert self._settings.nvidia_api_key is not None
        headers = {"Authorization": f"Bearer {self._settings.nvidia_api_key.get_secret_value()}"}
        payload = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": "You are a connectivity test. Reply exactly OK."},
                {"role": "user", "content": "healthcheck"},
            ],
            "temperature": 0,
        }
        started = perf_counter()
        try:
            if self._client is not None:
                response = self._client.post(
                    f"{NVIDIA_API_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=self._timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        f"{NVIDIA_API_BASE_URL}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
            response.raise_for_status()
            content = str(response.json()["choices"][0]["message"]["content"]).strip()
        except httpx.TimeoutException:
            return self._failure("NVIDIA request timed out", started)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            return self._failure("NVIDIA provider request failed", started)

        if content != "OK":
            return self._failure("NVIDIA provider returned an unexpected health response", started)
        return ServiceHealth(
            service="nvidia_llm_committee",
            status=HealthStatus.PASS,
            endpoint=NVIDIA_API_BASE_URL,
            message="deterministic connectivity response verified",
            latency_ms=_latency_ms(started),
        )

    @staticmethod
    def _failure(message: str, started: float) -> ServiceHealth:
        return ServiceHealth(
            service="nvidia_llm_committee",
            status=HealthStatus.FAIL,
            endpoint=NVIDIA_API_BASE_URL,
            message=message,
            latency_ms=_latency_ms(started),
        )


def _latency_ms(started: float) -> int:
    return round((perf_counter() - started) * 1000)