# AlphaCouncil PRE-M0 Bootstrap Report

## Repository

Absolute path: `C:\Users\gvnag\Documents\AlphaCouncil`

Git repository: initialized locally. No remote is configured and nothing has been pushed.

## Environment

| Component | Status | Version | Notes |
| --- | --- | --- | --- |
| Documents directory | PASS | — | Required parent directory exists. |
| Correct repository location | PASS | — | Exact required path. |
| Git | PASS | 2.51.2.windows.1 | Repository initialized. |
| Node.js | PASS | v24.19.0 | Available. |
| npm | BROKEN | — | Node's configured npm prefix points at a missing user installation. |
| pnpm | PASS | 11.20.0 | Available. |
| System Python | PASS | 3.14.6 | Available at `C:\Python314\python.exe`. |
| Project Python | PASS | 3.12.11 | Managed by uv. |
| uv / uvx | PASS | 0.8.17 | uvx is available. |
| Go | BLOCKED | — | Not installed; official winget installation did not complete. |
| Alpaca CLI | BLOCKED | — | Requires Go. |
| alpaca-py | PASS | 0.42.1 | Installed in the project-local uv environment and imported successfully. |
| Alpaca MCP prerequisites | BLOCKED | — | Requires Alpaca CLI/authentication. |
| Frontend | NOT REQUIRED | — | Deferred because npm is broken; no dashboard work was started. |

## Alpaca

- CLI: BLOCKED — not installed.
- Authentication: BLOCKED — no local API credentials or CLI authentication.
- Account, paper mode, clock, asset, market-data, positions, and orders read: BLOCKED — authentication/CLI unavailable.
- MCP prerequisites: BLOCKED — Go and Alpaca CLI unavailable.
- No Alpaca request or order submission occurred during PRE-M0.

## LLM

- Provider: NVIDIA (configured abstraction default).
- Connectivity: BLOCKED — `NVIDIA_API_KEY` and `LLM_MODEL` are not locally configured.
- No key is stored in this repository.

## Safety

| Setting | Status |
| --- | --- |
| `TRADING_MODE` | `paper` default enforced |
| `ENABLE_EXECUTION` | `false` default enforced |
| `ALPACA_LIVE_TRADE` | `false` default; `true` fails closed |
| Secret hygiene | PASS — `.env` ignored; placeholders only in `.env.example` |
| Orders submitted during PRE-M0 | ZERO |

## Verification

Python tests, Ruff lint, mypy typecheck, and the safe configuration diagnostic pass. A tracked-file secret scan is completed before the local commit. Frontend install/lint/typecheck/build are NOT REQUIRED until npm is repaired and the minimal app is intentionally scaffolded.

## Manual Actions Required

1. Install Go, then restart PowerShell. Open an elevated PowerShell and run:

   ```powershell
   winget install --id GoLang.Go --exact --source winget
   ```

   If Windows Package Manager cannot install it, download the official Windows x64 installer from `https://go.dev/dl/`, install it, and rerun `go version`.

2. Install the official Alpaca CLI after Go works:

   ```powershell
   go install github.com/alpacahq/cli/cmd/alpaca@latest
   ```

   If needed, add `$(go env GOPATH)\bin` to your user `Path`, restart PowerShell, then run `alpaca version` and `alpaca doctor`.

3. Repair npm before frontend setup. Reinstall the current Node LTS from `https://nodejs.org/` or use the official Windows Package Manager package, then verify `npm --version`.

4. Configure Alpaca paper credentials and NVIDIA credentials locally only in an untracked `.env` copied from `.env.example`. Never paste them into chat or commit them.

## Ready for M0?

NO

Blockers: Go/Alpaca CLI, Alpaca paper authentication/read-only verification, NVIDIA configuration, and npm repair. The Python bootstrap itself is ready to verify.
