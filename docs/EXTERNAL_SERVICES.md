# External Services

## Alpaca

The M0 integration boundary is `backend/app/alpaca/gateway.py`. It normalizes read-only Alpaca SDK responses into AlphaCouncil models and hides the raw SDK client from higher layers. `scripts/check_alpaca.py` uses this gateway and performs account, clock, AAPL asset, positions, and orders reads only.

## NVIDIA

`backend/app/llm/nvidia.py` owns the provider-specific call to `https://integrate.api.nvidia.com/v1/chat/completions`. It reads `LLM_MODEL`, sends a deterministic prompt with temperature zero, has a 30-second timeout, and makes no retries. Health responses expose service status, endpoint, safe message, and latency only; they never expose authorization data.

## MCP

Alpaca MCP is **DEFERRED** in M0. The current verified AlphaCouncil path uses the authenticated paper CLI OAuth profile. No OAuth values are copied into MCP configuration, and no MCP execution capability is introduced.
