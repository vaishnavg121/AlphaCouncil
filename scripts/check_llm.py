"""Safe NVIDIA LLM connectivity diagnostic."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings
from app.llm.nvidia import NvidiaLLMProvider


def main() -> int:
    settings = Settings()
    health = NvidiaLLMProvider(settings).healthcheck()
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model or 'MISSING'}")
    print(f"Connectivity: {health.status}")
    if health.latency_ms is not None:
        print(f"Latency: {health.latency_ms}ms")
    if health.message is not None:
        print(f"Detail: {health.message}")
    return 0 if health.status.value == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
