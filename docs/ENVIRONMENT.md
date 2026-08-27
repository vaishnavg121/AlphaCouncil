# Development Environment

AlphaCouncil assumes Windows 11 and PowerShell. The repository root is `C:\Users\gvnag\Documents\AlphaCouncil`.

## Python

The project pins managed CPython 3.12 through uv. From the repository root:

```powershell
uv sync --python 3.12
uv run pytest
uv run ruff check .
uv run mypy backend scripts tests
uv run python scripts/check_environment.py
```

## Node and pnpm

Node and pnpm are prerequisites for the future Next.js app. Use `pnpm` from `apps/web` only after that app is scaffolded. System npm must work before frontend scaffolding; PRE-M0 does not create a frontend while npm is broken.

## Go and Alpaca CLI

Install Go only from its official source or Windows Package Manager. Then restart PowerShell and verify:

```powershell
go version
go env GOPATH
go env GOBIN
go install github.com/alpacahq/cli/cmd/alpaca@latest
```

If `alpaca` is not found, add `$(go env GOPATH)\bin` (or `go env GOBIN` when non-empty) to the user `Path`, restart PowerShell, and run `alpaca version`. Use `alpaca --help` and `alpaca doctor` to discover the installed CLI's current read-only diagnostic and authentication syntax. Never place credentials in shell history or this repository.

## Local configuration

Copy `.env.example` to `.env` locally, then add credentials only to the untracked `.env` file. The required safe values are:

```text
TRADING_MODE=paper
ENABLE_EXECUTION=false
ALPACA_LIVE_TRADE=false
```

For NVIDIA, set `LLM_PROVIDER=nvidia`, `LLM_MODEL`, and `NVIDIA_API_KEY` locally. M0's `scripts/check_llm.py` sends one deterministic, 30-second-bounded request to NVIDIA's OpenAI-compatible endpoint. It never logs the authorization header or key and does not silently change models.

## Common safe diagnostics

```powershell
uv run python scripts/check_environment.py
uv run python scripts/check_alpaca.py
uv run python scripts/check_llm.py
```

`check_alpaca.py` only reads account, clock, and AAPL asset metadata. It submits no orders.

## Alpaca authentication

M0 resolves a complete credential bundle in this order: complete `ALPACA_API_KEY` plus `ALPACA_SECRET_KEY` environment pair; active paper-safe Alpaca CLI OAuth profile; active paper-safe CLI API-key pair. Partial values are never merged. The resolver reads the active profile from standard user configuration locations at runtime (including `~/.config/alpaca`), does not modify it, and never copies it to the repository or `.env`.

The standalone Alpaca MCP route remains deferred: it may require API keys, whereas the verified M0 path uses CLI OAuth. Do not copy OAuth values merely to satisfy MCP.
