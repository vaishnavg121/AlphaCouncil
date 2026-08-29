# Milestones

| Milestone | Scope | Status |
| --- | --- | --- |
| PRE | Environment/bootstrap: toolchain, repository, secrets/config, Alpaca read-only connectivity, MCP prerequisites, LLM connectivity, safety foundation. | ✅ COMPLETE |
| M0 | Alpaca foundation: paper-only gateway, typed contracts (AccountSnapshot, MarketClock, AssetInfo, PositionSnapshot, OrderSnapshot), safe order construction, validation, idempotency, controlled paper order test, lifecycle, execution safety. | ✅ COMPLETE |
| M1 | Market intelligence: historical bars, quotes, snapshots, technical features (RSI, SMA, EMA, ATR, realized vol, momentum, volume, drawdown), deterministic calculations, feature engine. | ✅ COMPLETE |
| M2 | Universe scanner: tradable universe (curated/Alpaca), liquidity filters, preliminary screening, deep analysis, diversification, candidate scoring, final selection. | ✅ COMPLETE |
| M3 | Agent committee: Quant, Bull, Bear, Regime agents; evidence-based reasoning; thesis synthesis; typed state graph; NO_TRADE/PROPOSE_LONG/PROPOSE_SHORT decisions. | ✅ COMPLETE |
| M4 | Deterministic risk engine: constitution (base risk/trade, max position, gross/net exposure, max positions, concentration, correlation); position sizing (ATR-based stops, risk budget, reductions); hard gates (kill switch, daily loss, max drawdown); soft reductions (volatility, liquidity, confidence, concentration, exposure). | ✅ COMPLETE |
| M5 | Instrument selection: equity planner (long/short, fractional, risk-budgeted); option gateway (chains, snapshots, Greeks, IV); option filters (DTE, moneyness, delta, spread, premium); option scoring (liquidity, Greeks, IV, moneyness); option sizing (contracts, max loss); equity vs option comparison with complexity margin; M4 REJECTED → NO_TRADE. | ✅ COMPLETE |
| **M6** | **Execution planning + safe paper execution**: ExecutionPlan with fresh quote validation, market hours policy, spread guard (2%), price deviation guard (0.5%), plan TTL (30s); deterministic LIMIT pricing (midpoint, tick-rounded); final M4 revalidation (kill switch, risk budget, max notional); defense-in-depth (quantity ceiling, notional ceiling, M5 ceiling); PaperExecutionGateway (only mutation boundary, paper-mode enforced); IdempotencyManager (deterministic keys + Alpaca client_order_id); ExecutionStore (SQLite, crash recovery); OrderTracker (bounded polling, 60s timeout); ExecutionReconciler (startup reconciliation); ExecutionService (orchestration, dry-run default); `ENABLE_PAPER_EXECUTION` opt-in; `scripts/check_execution.py` diagnostic. | ✅ **COMPLETE** |
| M7 | Position management & portfolio sync: position state tracking, thesis monitoring, exit rules, partial fills, portfolio reconciliation, kill switch integration. | 📋 PLANNED |
| M8 | Journal/trading memory: decision logging, post-trade evaluation, lessons learned, similarity retrieval. | 📋 PLANNED |
| M9 | Backtesting: simulation engine, benchmarks, Sharpe, drawdown, win rate, slippage analysis. | 📋 PLANNED |
| M10 | Advanced options: multi-leg strategies, dynamic hedging, volatility surface modeling. | 📋 PLANNED |
| M11 | Hardening/deployment/demo: reliability, observability, deployment automation, submission prep. | 📋 PLANNED |

---

## Current Verified State

**M6 Final Verification:**
- ✅ 321 tests passed, 1 skipped
- ✅ Ruff: 0 errors
- ✅ MyPy (execution module): 0 errors (strict mode)
- ✅ Security: `.env` untracked, no secrets in tracked files
- ✅ Zero mutations in dry run
- ✅ Mutation boundary enforced (M0-M5 mutation-free)
- ✅ All regression tests pass (M0-M5)