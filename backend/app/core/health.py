"""Secret-safe external-service health contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class HealthStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class ServiceHealth(BaseModel):
    """A diagnostic result containing only safe operational metadata."""

    model_config = ConfigDict(frozen=True)

    service: str
    status: HealthStatus
    auth_type: str | None = None
    endpoint: str | None = None
    message: str | None = None
    latency_ms: int | None = None
