# Execution Architecture (M6)

## Overview

The execution module (`backend/app/execution/`) implements M6: deterministic execution planning and safe Alpaca paper execution. It is the **only** package in AlphaCouncil authorized to perform trading mutations.

## Core Design Principles

1. **Mutation Boundary** - Only `PaperExecutionGateway` can call `submit_order`, `cancel_order`, etc.
2. **Fail-Closed** - Every validation failure results in `NOT_EXECUTED` or `DENIED`
3. **Deterministic** - Zero LLM calls, pure computation
4. **Paper-Only** - Structural impossibility of live trading
5. **Idempotent** - Duplicate protection via deterministic keys + Alpaca `client_order_id`
6. **Auditable** - Full lifecycle tracking: PLANNED → AUTHORIZED → SUBMITTED → FILLED/REJECTED/EXPIRED

## Module Structure

```
backend/app/execution/
├── __init__.py           # Public exports
├── models.py             # Typed contracts (ExecutionPlan, ExecutionResult, etc.)
├── gateway.py            # PaperExecutionGateway - ONLY mutation boundary
├── planner.py            # ExecutionPlanner - fresh data, limit price, TTL
├── validation.py         # ExecutionValidator - M4 revalidation, defense-in-depth
├── authorization.py      # ExecutionAuthorizer - deterministic authorization
├── idempotency.py        # IdempotencyManager - duplicate protection
├── store.py              # ExecutionStore - SQLite persistence
├── tracking.py           # OrderTracker - bounded status polling
├── reconciliation.py     # ExecutionReconciler - crash recovery
└── service.py            # ExecutionService - main orchestration
```

## Data Flow

```
M5 InstrumentPlan + M4 RiskEvaluation
         │
         ▼
┌─────────────────────────────────────┐
│ ExecutionPlanner                    │
│ • Fresh quote (bid/ask/mid)         │
│ • Market hours check                │
│ • Spread validation                 │
│ • Asset tradability                 │
│ • Shortability (bearish equity)     │
│ • Limit price (mid, tick-rounded)   │
│ • Price deviation check (0.5%)      │
│ • TTL = 30s                         │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ ExecutionValidator                  │
│ • Config: ENABLE_PAPER_EXECUTION    │
│ • Upstream: M3 NO_TRADE, M4 REJECT  │
│ • M4: RiskBudget, kill switch       │
│ • Plan: qty ≤ M5, notional ≤ M4     │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ ExecutionAuthorizer                 │
│ • Aggregates all reason codes       │
│ • Returns AUTHORIZED or DENIED      │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ IdempotencyManager                  │
│ • Local store check (idempotency_key)│
│ • Provider check (client_order_id)  │
│ • Adopt existing if found           │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ PaperExecutionGateway               │
│ • Enforces paper mode               │
│ • submit_limit_order()              │
│ • get_order_by_client_id()          │
│ • cancel_order() (AlphaCouncil only)│
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ OrderTracker (optional)             │
│ • Polls for terminal state          │
│ • Timeout = 60s, interval = 2s      │
└─────────────────────────────────────┘
         │
         ▼
      ExecutionResult
```

## Key Models

### ExecutionPlan
```python
execution_plan_id: str           # Deterministic from idempotency key
instrument_plan_id: str          # Links to M5 plan
created_at / expires_at: datetime # TTL = 30s
symbol: str
instrument_type: InstrumentType  # STOCK, ETF, OPTION
direction: "BULLISH" | "BEARISH"
side: OrderSide                  # BUY | SELL
quantity: Decimal
order_type: OrderType            # LIMIT (preferred) | MARKET
time_in_force: TimeInForce       # DAY
m5_reference_price: Decimal      # M5 planning reference
fresh_bid/ask/mid: Decimal       # Fresh market quote
fresh_quote_timestamp: datetime
limit_price: Decimal             # Calculated limit price
expected_notional: Decimal
risk_budget: Decimal             # M4 adjusted risk budget
max_authorized_notional: Decimal # M4 max position notional
constitution_version: str
```

### ExecutionAuthorization
```python
execution_plan_id: str
state: ExecutionAuthorizationState  # AUTHORIZED | DENIED
reason_code: ExecutionReasonCode    # 25+ exhaustive codes
checks: tuple[str, ...]             # Audit trail
authorized_at: datetime
```

### ExecutionResult
```python
execution_plan_id: str
instrument_plan_id: str
status: ExecutionStatus  # PLANNED, AUTHORIZED, SUBMITTED, PARTIALLY_FILLED,
                         # FILLED, REJECTED, CANCELED, EXPIRED, NOT_EXECUTED, UNKNOWN, FAILED
authorization: ExecutionAuthorization
execution_plan: ExecutionPlan
execution_order: ExecutionOrder | None
warnings: tuple[str, ...]
reason_codes: tuple[ExecutionReasonCode, ...]
timestamps: created_at, authorized_at, submitted_at, completed_at
```

## Usage

### Dry Run (Default)
```python
from app.execution import create_execution_service

service = create_execution_service(settings, market_gateway, alpaca_gateway)
result = service.execute(instrument_plan, risk_evaluation, dry_run=True)

if result.authorization.is_authorized:
    print(f"Would submit: {result.execution_plan}")
else:
    print(f"Denied: {result.authorization.reason_code}")
```

### Paper Execution (Requires Opt-In)
```bash
# .env
ENABLE_EXECUTION=true
ENABLE_PAPER_EXECUTION=true
TRADING_MODE=paper
ALPACA_LIVE_TRADE=false
```

```python
result = service.execute(
    instrument_plan,
    risk_evaluation,
    dry_run=False,   # Actually submits
    track=True       # Polls for fill
)
```

### Crash Recovery
```python
# On startup
results = service.reconcile_all()
for r in results:
    if r.reconciled:
        print(f"Recovered: {r.local_record.execution_plan_id} -> {r.action_taken}")
```

## Testing

```bash
# All tests
pytest tests/ -v

# Execution-specific (when added)
pytest tests/test_execution_*.py -v
```