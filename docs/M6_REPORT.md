# M6 Execution Planning + Safe Alpaca Paper Execution

## Status: COMPLETE

All M6 objectives have been implemented and verified.

## Overview

M6 is the first milestone where AlphaCouncil becomes capable of submitting REAL Alpaca PAPER orders. It maintains the absolute prohibition on live trading while introducing a safe, deterministic execution pipeline with defense-in-depth safety checks.

## Architecture

### Core Components

| Component | Purpose |
|-----------|---------|
| `ExecutionPlan` | Typed execution plan with fresh market data, limit price, TTL |
| `ExecutionAuthorization` | Deterministic authorization with structured reason codes |
| `ExecutionResult` | Complete execution lifecycle result |
| `ExecutionOrder` | Normalized provider order representation |
| `PaperExecutionGateway` | **Only mutation boundary** - enforces paper-only mode |
| `ExecutionPlanner` | Fresh market validation, limit price planning, TTL |
| `ExecutionValidator` | Final M4 revalidation, defense-in-depth checks |
| `ExecutionAuthorizer` | Deterministic authorization with exhaustive reason codes |
| `IdempotencyManager` | Duplicate protection via idempotency keys + client_order_id |
| `ExecutionStore` | SQLite persistence for crash recovery |
| `OrderTracker` | Bounded order status polling |
| `ExecutionReconciler` | Crash recovery reconciliation |
| `ExecutionService` | Main orchestration service |

### Pipeline Flow

```
M5 InstrumentPlan
        ↓
ExecutionPlanner (fresh quote validation, limit price)
        ↓
ExecutionValidator (M4 revalidation, kill switch, notional checks)
        ↓
ExecutionAuthorizer (authorization with reason codes)
        ↓
IdempotencyManager (local + provider duplicate check)
        ↓
PaperExecutionGateway (paper-only mutation boundary)
        ↓
OrderTracker (bounded status polling)
        ↓
ExecutionResult
```

## Safety Guarantees

### Paper-Only Enforcement
- `TRADING_MODE` must be `"paper"` (Literal type)
- `ALPACA_LIVE_TRADE` must be `false` (validated at config load)
- `ENABLE_PAPER_EXECUTION` must be `true` for gateway operations
- Gateway enforces all three at construction AND every mutation call
- No `paper=False` construction possible
- No live trading endpoint exists

### Defense in Depth
1. **Config validation** - Rejects invalid flag combinations at startup
2. **Upstream gates** - M3 NO_TRADE / M4 REJECTED / missing RiskBudget → DENIED
3. **M4 revalidation** - Kill switch, RiskBudget, max notional checked immediately before submission
4. **Plan validation** - Quantity ≤ M5, notional ≤ M4 budget, plan TTL not expired
5. **Market validation** - Fresh quote, spread guard, price deviation guard, market hours
6. **Idempotency** - Deterministic key + Alpaca client_order_id dual protection
6. **Mutation boundary** - Only `PaperExecutionGateway` can call `submit_order`

### What M6 Can NEVER Do
- Increase M4 risk budget
- Increase M4 max position notional
- Increase M5 quantity
- Increase M5 option contract count
- Bypass kill switch
- Execute M5 NO_TRADE or M4 REJECTED
- Execute with stale plan (>30s TTL)
- Execute with stale quote
- Ignore price movement > 0.5%
- Use MARKET orders by default (LIMIT preferred)
- Chase unfilled limit orders
- Cancel unrelated orders
- Execute naked short options or multi-leg strategies

## Configuration

### New Settings (`.env`)

```bash
# M6 Execution Configuration
ENABLE_PAPER_EXECUTION=false          # Default false - must opt-in
MAX_EXECUTION_PRICE_DEVIATION_PCT=0.005   # 0.5% max deviation from M5 reference
MAX_EXECUTION_SPREAD_PCT=0.02             # 2% max bid-ask spread
EXECUTION_PLAN_TTL_SECONDS=30             # Plan expires after 30s
EXECUTION_TRACK_TIMEOUT_SECONDS=60        # Max tracking time
EXECUTION_POLL_INTERVAL_SECONDS=2.0       # Poll interval
EXECUTION_DIAGNOSTIC_MAX_NOTIONAL=500.0   # Diagnostic cap ($500)
```

### Config Validation
```python
# Fail-closed validation
if enable_paper_execution and not enable_execution:
    raise ValueError("ENABLE_PAPER_EXECUTION requires ENABLE_EXECUTION=true")
if enable_paper_execution and trading_mode != "paper":
    raise ValueError("ENABLE_PAPER_EXECUTION requires TRADING_MODE=paper")
if enable_paper_execution and alpaca_live_trade:
    raise ValueError("ENABLE_PAPER_EXECUTION requires ALPACA_LIVE_TRADE=false")
```

## Diagnostic Script

```bash
# Dry run (default - ZERO mutations)
uv run python scripts/check_execution.py

# Real paper submission (requires ENABLE_PAPER_EXECUTION=true)
uv run python scripts/check_execution.py --paper-submit
```

### Dry Run Output Example
```
M6 EXECUTION DIAGNOSTIC
============================================================
Trading Mode:           paper
Enable Execution:       False
Enable Paper Execution: False
Alpaca Live Trade:      False
...

SCENARIO A: M3 NO_TRADE (Expected: NOT_EXECUTED)
...
  M4 Risk Evaluation:
    Decision: REJECTED
    Reason:   M3_NO_TRADE
  M5 Instrument Selection:
    Result: NO_TRADE
    Reason: RISK_REJECTED
  M6 Execution (DRY RUN):
    Status: NOT_EXECUTED
    Auth State: DENIED
    Auth Reason: RISK_REJECTED
  EXPECTATION: PASS

SCENARIO B: SYNTHETIC M4 APPROVAL + REAL DATA
...
  M4 Risk Evaluation:
    Decision: APPROVED
    Reason:   WITHIN_LIMITS
  Risk Budget:
    Base:              $1,000.00
    Adjusted:          $850.00
    Max Notional:      $5,000.00
  M5 Instrument Selection:
    Result: STOCK
    Side: LONG
    Est Qty: 8
    Max Notional: $5,000.00
    Planned Notional: $4,250.00
  M6 Execution (DRY RUN):
    Status: AUTHORIZED
    Auth State: AUTHORIZED
    Auth Reason: WITHIN_LIMITS
    Execution Plan:
      Symbol: SPY
      Type: STOCK
      Side: BUY
      Quantity: 8
      Order Type: LIMIT
      Limit Price: $531.25
      Price Deviation: 0.02%
    Warnings:
      - DRY RUN - Would submit LIMIT BUY 8 SPY @ 531.25
      - DRY RUN - Client Order ID: ac-xxx...
  EXPECTATION: PASS
```

## Testing Results

| Test Category | Status |
|---------------|--------|
| Config safety (ENABLE_PAPER_EXECUTION=false → no mutation) | ✅ PASS |
| Config safety (TRADING_MODE!=paper → no mutation) | ✅ PASS |
| Config safety (ALPACA_LIVE_TRADE=true → no mutation) | ✅ PASS |
| Config safety (invalid combination → fail closed) | ✅ PASS |
| Upstream gates (M5 NO_TRADE → no execution) | ✅ PASS |
| Upstream gates (M4 REJECTED → no execution) | ✅ PASS |
| Upstream gates (kill switch → no execution) | ✅ PASS |
| Upstream gates (missing RiskBudget → no execution) | ✅ PASS |
| Upstream gates (expired plan → no execution) | ✅ PASS |
| Market validation (fresh valid quote) | ✅ PASS |
| Market validation (stale quote → DENY) | ✅ PASS |
| Market validation (crossed quote → DENY) | ✅ PASS |
| Market validation (zero bid/ask → DENY) | ✅ PASS |
| Market validation (wide spread → DENY) | ✅ PASS |
| Market validation (price moved too far → DENY) | ✅ PASS |
| Market validation (market closed → NOT_EXECUTED) | ✅ PASS |
| Market validation (asset not tradable → DENY) | ✅ PASS |
| Market validation (asset not shortable → DENY) | ✅ PASS |
| Price planning (BUY limit) | ✅ PASS |
| Price planning (SELL limit) | ✅ PASS |
| Price planning (Decimal arithmetic) | ✅ PASS |
| Price planning (tick/precision) | ✅ PASS |
| Price planning (bounded aggressiveness) | ✅ PASS |
| Quantity (M5=10 → M6≤10) | ✅ PASS |
| Quantity (zero → rejected) | ✅ PASS |
| M4 ceiling (malformed M5 exceeding M4 → DENIED) | ✅ PASS |
| Idempotency (10x execute → 1 submit) | ✅ PASS |
| Ambiguous timeout (submit timeout → adopt existing) | ✅ PASS |
| Crash recovery (restart → reconcile → 0 duplicates) | ✅ PASS |
| Order states (SUBMITTED/PARTIALLY_FILLED/FILLED/CANCELED/REJECTED/EXPIRED/UNKNOWN) | ✅ PASS |
| Dry run (0 gateway calls) | ✅ PASS |
| Mutation boundary (M0-M5 mutation-free) | ✅ PASS |

## Quality Gates

| Check | Status |
|-------|--------|
| `pytest` (321 passed, 1 skipped) | ✅ PASS |
| `ruff check` | ✅ PASS |
| `mypy --strict` (execution module) | ✅ PASS |
| Security (`.env` untracked, no secrets) | ✅ PASS |

## Regression

| Milestone | Status |
|-----------|--------|
| M0 External Services & Safety | ✅ PASS |
| M1 Deterministic Market Intelligence | ✅ PASS |
| M2 Opportunity Discovery | ✅ PASS |
| M3 Adversarial Investment Committee | ✅ PASS |
| M4 Deterministic Risk Constitution | ✅ PASS |
| M5 Deterministic Instrument Selection | ✅ PASS |

## Files Created/Modified

### New Files
- `backend/app/execution/__init__.py`
- `backend/app/execution/models.py`
- `backend/app/execution/gateway.py`
- `backend/app/execution/planner.py`
- `backend/app/execution/validation.py`
- `backend/app/execution/authorization.py`
- `backend/app/execution/idempotency.py`
- `backend/app/execution/store.py`
- `backend/app/execution/tracking.py`
- `backend/app/execution/reconciliation.py`
- `backend/app/execution/service.py`
- `scripts/check_execution.py`

### Modified Files
- `backend/app/core/config.py` - Added M6 settings + validation
- `backend/app/core/errors.py` - Added `ExecutionError`, `MarketDataError`
- `tests/test_config.py` - Updated execution config tests
- `tests/test_diagnostics.py` - Excluded execution module from mutation scan

## Ready for M7

M6 is complete and ready for M7 (Position Management & Portfolio Sync).