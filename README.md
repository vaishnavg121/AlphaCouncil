# AlphaCouncil

AlphaCouncil is an explainable, adversarial multi-agent autonomous **paper-trading** project for the Alpaca AI Trading Agents Hackathon. Its intended design separates market intelligence and LLM proposals from deterministic risk controls and a final paper-only execution gate.

**Status: M6 complete — Safe deterministic execution with paper-only Alpaca gateway.** The repository now supports full M6 execution planning, fresh market validation, deterministic limit pricing, idempotent paper execution, crash recovery, and bounded order tracking.

## Safety

PAPER TRADING ONLY. Keep `TRADING_MODE=paper`, `ENABLE_EXECUTION=false`, `ENABLE_PAPER_EXECUTION=false`, and `ALPACA_LIVE_TRADE=false`. Do not commit `.env` or credentials.

## Local Setup

```powershell
Copy-Item .env.example .env
uv sync --python 3.12
uv run pytest
uv run ruff check .
uv run mypy backend scripts tests
uv run python scripts/check_environment.py
uv run python scripts/check_alpaca.py
uv run python scripts/check_market_data.py
uv run python scripts/check_discovery.py
uv run python scripts/check_risk.py
uv run python scripts/check_instruments.py
uv run python scripts/check_execution.py      # M6: dry run (ZERO mutations)
```

See [environment setup](docs/ENVIRONMENT.md), the [safety policy](docs/SAFETY.md), [planned architecture](docs/ARCHITECTURE.md), and [milestones](docs/MILESTONES.md).

## Milestones

| Milestone | Status | Description |
|-----------|--------|-------------|
| M0 | ✅ COMPLETE | External Services & Safety |
| M1 | ✅ COMPLETE | Deterministic Market Intelligence |
| M2 | ✅ COMPLETE | Opportunity Discovery |
| M3 | ✅ COMPLETE | Adversarial Investment Committee |
| M4 | ✅ COMPLETE | Deterministic Risk Constitution |
| M5 | ✅ COMPLETE | Deterministic Instrument Selection |
| **M6** | ✅ **COMPLETE** | **Execution Planning + Safe Paper Execution** |
| M7 | 📋 PLANNED | Position Management & Portfolio Sync |

## M6 Quick Start

### Dry Run (Default - Zero Mutations)
```bash
uv run python scripts/check_execution.py
```

### Paper Execution (Explicit Opt-In Required)
```bash
# .env must have:
# ENABLE_EXECUTION=true
# ENABLE_PAPER_EXECUTION=true
# TRADING_MODE=paper
# ALPACA_LIVE_TRADE=false
uv run python scripts/check_execution.py --paper-submit
```

### Expected Dry Run Output
```
M6 EXECUTION DIAGNOSTIC
============================================================
Trading Mode:           paper
Enable Execution:       False
Enable Paper Execution: False
...

SCENARIO A: M3 NO_TRADE
  M6 Execution (DRY RUN):
    Status: NOT_EXECUTED
    Auth State: DENIED
    Auth Reason: RISK_REJECTED
  EXPECTATION: PASS

SCENARIO B: SYNTHETIC M4 APPROVAL + REAL DATA
  M4 Risk Evaluation:
    Decision: APPROVED
    Reason:   WITHIN_LIMITS
    Base:     $1,000.00
    Adjusted: $850.00
    Max Notional: $5,000.00
  M5 Instrument Selection:
    Result: STOCK
    Side: LONG
    Est Qty: 8
  M6 Execution (DRY RUN):
    Status: AUTHORIZED
    Auth State: AUTHORIZED
    Auth Reason: WITHIN_LIMITS
    Limit Price: $531.25
    Price Deviation: 0.02%
  EXPECTATION: PASS

OVERALL: PASS
```

## Documentation

| Document | Description |
|----------|-------------|
| [M6 Report](docs/M6_REPORT.md) | Complete M6 implementation summary |
| [Execution Architecture](docs/EXECUTION.md) | Technical architecture guide |
| [Execution Safety](docs/EXECUTION_SAFETY.md) | Safety guarantees and prohibitions |
| [Risk Constitution](docs/RISK_CONSTITUTION.md) | M4 deterministic risk rules |
| [Instrument Selection](docs/INSTRUMENT_SELECTION.md) | M5 equity/option planning |
| [Market Data](docs/MARKET_DATA.md) | M1 market intelligence |
| [Discovery](docs/DISCOVERY.md) | M2 opportunity discovery |
| [Committee](docs/COMMITTEE.md) | M3 adversarial agents |
| [Options Selection](docs/OPTIONS_SELECTION.md) | M5 options pipeline |