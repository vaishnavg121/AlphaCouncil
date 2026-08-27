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
| NVIDIA | PASS | `nvidia/nemotron-3-nano-30b-a3b` connectivity verified at `https://integrate.api.nvidia.com/v1`. Latency ~1050ms. Initial model `nvidia/nemotron-3.5-lightning-30b-a3b` returned 404 "Function not found for account"; replaced with working same-family 30b model. |
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

The default test suite is offline and deterministic. The Alpaca and NVIDIA scripts are explicit integration diagnostics; both now pass real connectivity.

## Final M0 Gate Summary

### NVIDIA
- **Endpoint**: `https://integrate.api.nvidia.com/v1`
- **Configured model**: `nvidia/nemotron-3-nano-30b-a3b` (was `nvidia/nemotron-3.5-lightning-30b-a3b`)
- **Connectivity result**: PASS
- **Latency**: ~1050ms
- **Failure cause discovered**: Initial model `nvidia/nemotron-3.5-lightning-30b-a3b` listed in catalog but returned 404 "Function not found for account" on chat/completions — not enabled for this NVIDIA account.
- **Fix applied**: Changed `LLM_MODEL` in `.env` to `nvidia/nemotron-3-nano-30b-a3b` (same 30b parameter count, Nemotron 3 family, chat/completions enabled).

### Alpaca
- **PAPER confirmed**: Yes
- **OAuth profile**: Active CLI profile resolved
- **Read operations**: PASS (account, clock, AAPL asset, positions, orders)
- **Orders submitted**: 0

### Tests
- **pytest**: 23 passed
- **Ruff**: PASS
- **mypy**: PASS

### Security
- **.env tracked**: NO
- **Secrets committed**: NO

### Git
- **Branch**: master
- **Commit hash**: 89e69967b09e75742eb091619f19b50bc5b240b6
- **Worktree state**: Clean (no tracked changes; `.env` is untracked)

---

**READY FOR M1: YES**
