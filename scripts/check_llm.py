"""Safe NVIDIA LLM prerequisite diagnostic.

No request is made until both a credential and a model are configured locally.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings


def main() -> int:
    settings = Settings()
    if not settings.nvidia_credentials_configured:
        print("BLOCKED — NVIDIA_API_KEY REQUIRED")
        return 2
    if not settings.llm_model:
        print("BLOCKED — LLM_MODEL REQUIRED before a connectivity request")
        return 2
    print("BLOCKED — provider endpoint selection is deferred to M0; no request made")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
