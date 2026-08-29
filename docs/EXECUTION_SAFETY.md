# Execution Safety (M6)

## Absolute Prohibitions

The following are **structurally impossible** in the M6 architecture:

| Prohibition | Enforcement |
|-------------|-------------|
| Live trading | `ALPACA_LIVE_TRADE` must be `false` (config validator) |
| `paper=False` construction | `TradingClient` always created with `paper=True` |
| Live endpoint | No `/execution/live` route exists |
| Automatic live transition | No code path enables live mode |
| Mutation outside gateway | Only `PaperExecutionGateway` has mutation methods |
| Execution with `ENABLE_PAPER_EXECUTION=false` | Gateway constructor raises `ExecutionError` |

## Fail-Closed Defaults

| Setting | Default | Purpose |
|---------|---------|---------|
| `ENABLE_EXECUTION` | `false` | Global execution toggle |
| `ENABLE_PAPER_EXECUTION` | `false` | Paper execution opt-in |
| `TRADING_MODE` | `"paper"` | Literal type - only "paper" allowed |
| `ALPACA_LIVE_TRADE` | `false` | Explicit live prohibition |

## Config Validation (Fail-Closed)

```python
@model_validator(mode="after")
def validate_execution_config(self) -> Settings:
    if self.enable_paper_execution and not self.enable_execution:
        raise ValueError("ENABLE_PAPER_EXECUTION requires ENABLE_EXECUTION=true")
    if self.enable_paper_execution and self.trading_mode != "paper":
        raise ValueError("ENABLE_PAPER_EXECUTION requires TRADING_MODE=paper")
    if self.enable_paper_execution and self.alpaca_live_trade:
        raise ValueError("ENABLE_PAPER_EXECUTION requires ALPACA_LIVE_TRADE=false")
    return self
```

## Defense in Depth Layers

### Layer 1: Configuration
- Invalid combinations rejected at startup
- `.env` validation before any broker connection

### Layer 2: Upstream Gates
| Gate | Check | Result if Failed |
|------|-------|------------------|
| M3 NO_TRADE | `instrument_plan.instrument_type == NO_TRADE` | `UPSTREAM_NO_TRADE` |
| M4 REJECTED | `risk_evaluation.decision == REJECTED` | `RISK_REJECTED` |
| Missing RiskBudget | `risk_evaluation.risk_budget is None` | `RISK_BUDGET_MISSING` |
| Kill Switch | `risk_state.kill_switch_active` | `KILL_SWITCH_ACTIVE` |

### Layer 3: M4 Revalidation (Immediate Pre-Submission)
| Check | Limit | Failure Code |
|-------|-------|--------------|
| RiskBudget exists | Required | `RISK_BUDGET_MISSING` |
| Kill switch | Inactive | `KILL_SWITCH_ACTIVE` |
| Max position notional | M4 ceiling | `NOTIONAL_EXCEEDED` |
| Risk budget | M4 adjusted budget | `RISK_BUDGET_EXCEEDED` |
| Constitution version | Current | `INTERNAL_VALIDATION_FAILED` |

### Layer 4: Plan Validation
| Check | Rule | Failure Code |
|-------|------|--------------|
| Plan TTL | ≤ 30s from creation | `PLAN_EXPIRED` |
| Quantity | > 0 and ≤ M5 quantity | `INVALID_QUANTITY` |
| Notional | ≤ M4 max notional | `NOTIONAL_EXCEEDED` |
| Notional | ≤ M4 risk budget | `RISK_BUDGET_EXCEEDED` |
| Option max loss | ≤ M4 risk budget | `RISK_BUDGET_EXCEEDED` |

### Layer 5: Market Validation
| Check | Rule | Failure Code |
|-------|------|--------------|
| Market hours | Regular session open | `MARKET_CLOSED` |
| Quote freshness | Bid > 0, Ask > 0 | `INVALID_QUOTE` |
| Quote quality | Bid < Ask (no cross) | `INVALID_QUOTE` |
| Spread | ≤ 2% of mid | `SPREAD_TOO_WIDE` |
| Price deviation | ≤ 0.5% from M5 ref | `PRICE_MOVED_TOO_FAR` |
| Asset tradable | `asset.tradable == true` | `ASSET_NOT_TRADABLE` |
| Asset shortable | `shortable && easy_to_borrow` | `ASSET_NOT_SHORTABLE` |

### Layer 6: Idempotency / Duplicate Protection
| Mechanism | Purpose |
|-----------|---------|
| Deterministic idempotency key | `ac-{plan_id[:8]}-{symbol}-{side}-{qty}-{risk_version[:8]}` |
| Alpaca `client_order_id` | Second deduplication layer |
| Local store check | Before submission |
| Provider check | `get_order_by_client_id()` |
| Adopt existing | Never submit duplicate |

### Layer 7: Mutation Boundary
- Only `PaperExecutionGateway` can call:
  - `submit_order()` (LIMIT/MARKET)
  - `cancel_order_by_id()` (AlphaCouncil-owned only)
  - `get_order_by_client_id()` (deduplication)
- Gateway enforces paper mode at:
  - Construction time
  - Every mutation method entry

## What M6 Can NEVER Do

| Action | Prevention |
|--------|------------|
| Increase M4 risk budget | Plan validation rejects |
| Increase M4 max position notional | Plan validation rejects |
| Increase M5 quantity | Plan validation (`qty ≤ M5 qty`) |
| Increase M5 option contracts | Plan validation (`contracts ≤ M5 contracts`) |
| Bypass kill switch | Layer 2 + 3 revalidation |
| Execute M5 NO_TRADE | Layer 2 gate |
| Execute M4 REJECTED | Layer 2 gate |
| Execute stale plan (>30s) | Plan TTL check |
| Execute stale quote | Fresh quote fetched per execution |
| Ignore price movement > 0.5% | Price deviation guard |
| Use MARKET orders by default | LIMIT is only default; MARKET requires explicit opt-in |
| Chase unfilled limit orders | No cancel/replace logic; reports SUBMITTED |
| Cancel unrelated orders | `cancel_order` only for AlphaCouncil orders |
| Execute naked short options | Only `BUY_TO_OPEN` (long CALL/PUT) |
| Execute multi-leg options | No multi-leg support in M6 |

## Idempotency Design

### Deterministic Key Generation
```python
IdempotencyKey(
    instrument_plan_id=instrument_plan.plan_id,
    symbol=symbol,
    side=OrderSide.BUY/SELL,
    quantity=Decimal,           # Exact M5 quantity
    risk_authorization_version=risk_evaluation.constitution_version
)
# Produces: ac-{plan_id[:8]}-{symbol}-{side}-{qty}-{version[:8]}
```

### Dual Protection
1. **Local**: `ExecutionStore.get_by_idempotency_key()`
2. **Provider**: `TradingClient.get_order_by_client_id()`

### Ambiguous Timeout Handling
```
submit_order() → timeout
       │
       ▼
get_order_by_client_id(client_order_id)
       │
       ├─► Found → Adopt existing order (0 duplicates)
       │
       └─► Not found → Bounded retry (max 1)
```

## Crash Recovery

### Reconciliation Flow
```
On startup:
  1. ExecutionStore.get_pending_executions()  # AUTHORIZED, no provider_order_id
  2. ExecutionStore.get_active_executions()   # Has provider_order_id, non-terminal
  3. For each: reconcile via provider_order_id → client_order_id
  4. Update local state with provider status
  5. NEVER create second order
```

### Reconciliation Results
| Scenario | Action |
|----------|--------|
| Provider order found | Update local state to provider status |
| Provider order not found | Mark `UNKNOWN_PROVIDER` (likely expired/canceled) |
| Multiple matches | Log warning, adopt first |

## Testing Safety Properties

```bash
# Config safety
pytest tests/test_config.py::test_execution_requires_paper_mode -v
pytest tests/test_config.py::test_execution_requires_live_false -v
pytest tests/test_config.py::test_execution_requires_all_paper_flags -v

# Mutation boundary
pytest tests/test_diagnostics.py::test_no_m0_source_contains_alpaca_mutation_calls -v

# Dry run = 0 mutations
pytest tests/ -k "dry_run" -v
```

## Diagnostic Safety

```bash
# Default: DRY RUN, ZERO mutations
uv run python scripts/check_execution.py

# Paper submission: EXPLICIT opt-in, requires all flags
uv run python scripts/check_execution.py --paper-submit
# Refuses if:
# - ENABLE_PAPER_EXECUTION=false
# - ALPACA_LIVE_TRADE=true
# - Market closed (reports SKIPPED, not failure)
```

## Security

- No credentials in execution store
- No secrets in logs (only order IDs, symbols, quantities)
- `.env` in `.gitignore` (verified by `git ls-files .env`)
- No credential patterns in tracked files