# AlphaCouncil

AlphaCouncil is an explainable, adversarial multi-agent autonomous **paper-trading** project for the Alpaca AI Trading Agents Hackathon. Its intended design separates market intelligence and LLM proposals from deterministic risk controls and a final paper-only execution gate.

**Status: M0 safe external-service foundation.** The repository has a paper-only, read-only Alpaca gateway and a minimal NVIDIA connectivity provider. No trading system, strategy, agents, dashboard, orders, or execution logic exists yet.

## Safety

PAPER TRADING ONLY. Keep `TRADING_MODE=paper`, `ENABLE_EXECUTION=false`, and `ALPACA_LIVE_TRADE=false`. Do not commit `.env` or credentials.

## Local setup

```powershell
Copy-Item .env.example .env
uv sync --python 3.12
uv run pytest
uv run ruff check .
uv run mypy backend scripts tests
uv run python scripts/check_environment.py
```

See [environment setup](docs/ENVIRONMENT.md), the [safety policy](docs/SAFETY.md), [planned architecture](docs/ARCHITECTURE.md), and [milestones](docs/MILESTONES.md).
