# AlphaCouncil M0 Report — Safe External Service Foundation

## Implemented

- Fail-closed settings: paper mode only, live trading false, and execution disabled.
- Atomic Alpaca API-key and active CLI OAuth credential resolution.
- PAPER-only Alpaca client factory and read-only gateway.
- Typed service-health and normalized Alpaca read models.
- Bounded NVIDIA OpenAI-compatible connectivity provider.
- Offline mocked tests and real diagnostic scripts.

## Real-service verification

| Service | Status | Result |
| --- | --- | --- |
| Alpaca authentication | PASS | Active PAPER CLI OAuth profile resolved. |
| Alpaca account | PASS | Read-only account request connected. |
| Alpaca clock | PASS | Read succeeded. |
| Alpaca AAPL asset | PASS | Read succeeded. |
| Alpaca positions | PASS | Read succeeded. |
| Alpaca orders | PASS | Read succeeded. |
| Orders submitted | PASS | Zero. |
| NVIDIA | BLOCKED | Initial configured-model request timed out at 15 seconds. A later 30-second-bounded diagnostic attempt produced no captured completion, so connectivity is not treated as passed. No model fallback was used. |
| Alpaca MCP | DEFERRED | The verified M0 OAuth path is not copied into MCP configuration. |

## Safety state

`TRADING_MODE=paper`, `ENABLE_EXECUTION=false`, and `ALPACA_LIVE_TRADE=false` were confirmed through the local configuration diagnostic. All Alpaca SDK client creation uses `paper=True`; no M0 source includes order, cancellation, closure, liquidation, locate, or option-exercise calls.

## Verification commands

```powershell
uv sync
uv run pytest -v
uv run ruff check .
uv run mypy .
uv run python scripts/check_environment.py
uv run python scripts/check_alpaca.py
uv run python scripts/check_llm.py
```

The default test suite is offline and deterministic. The Alpaca and NVIDIA scripts are explicit integration diagnostics; only the Alpaca script is currently passing real connectivity.
