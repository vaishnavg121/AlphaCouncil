# AlphaCouncil Instrument Selection (M5)

## Overview

M5 Instrument Selection determines the optimal instrument (stock/ETF vs. long option) to express an M3 thesis that has passed M4 risk evaluation. It operates deterministically with **zero LLM calls** and **zero trading mutations**.

## Pipeline

```
TradeThesis (M3) + RiskEvaluation (M4) + MarketState (M1)
         ↓
    InstrumentSelectorService
         ↓
┌─────────────────────┬─────────────────────┐
│  Equity Alternative │  Option Alternative │
│  (Stock/ETF)        │  (Long CALL/PUT)    │
└─────────────────────┴─────────────────────┘
         ↓
    Deterministic Comparison
         ↓
    InstrumentPlan (STOCK | OPTION | NO_TRADE)
```

## Core Principles

1. **M4 Authority**: M4 RiskBudget is an immutable ceiling. M5 never exceeds it.
2. **Defined Loss Only**: Options provide bounded premium loss; no naked short or multi-leg.
3. **Deterministic**: Same inputs → same InstrumentPlan every time.
4. **Fail-Safe**: If neither instrument is viable → NO_TRADE.
5. **M4 Gate**: M4 REJECTED ⇒ immediate NO_TRADE (RISK_REJECTED), zero option chain fetches.

## Equity Alternative

### Planning
- Reference price: quote midpoint → last trade → daily close
- Max notional: `RiskBudget.max_position_notional` (M4 ceiling)
- Provisional stop: M4 ATR-based stop distance
- Target notional: `min(adjusted_risk_budget / stop_distance_pct, max_notional)`
- Quantity: `planned_notional / ref_price` (fractional if supported, else whole shares)

### Risk Estimate
- `estimated_loss_at_risk_stop = planned_notional × stop_distance_pct`
- Must satisfy: `estimated_loss_at_risk_stop ≤ adjusted_risk_budget`
- Note: This is an **estimate**, not a guaranteed max loss (stops can gap)

### Scoring Factors
- Underlying liquidity (avg volume)
- Spread tightness
- Data quality
- Risk budget utilization efficiency

## Option Alternative

### Supported Types
- **LONG CALL** for BULLISH thesis
- **LONG PUT** for BEARISH thesis
- **NO** naked short, covered calls, spreads, multi-leg

### Universe Filtering
1. Correct underlying symbol
2. Correct option type (CALL/PUT per thesis direction)
3. Expiry window: `MIN_DTE ≤ DTE ≤ MAX_DTE` (default 7-90, target 21-60)
4. Moneyness: `MIN_MONEYNESS ≤ moneyness ≤ MAX_MONEYNESS` (default 0.85-1.15)
5. Delta (if available): `HARD_ABS_DELTA_MIN ≤ |delta| ≤ HARD_ABS_DELTA_MAX`
5. Active/tradable status

### Market Data Requirements
- Valid quote (bid > 0, ask > 0, bid ≤ ask)
- Spread ≤ `MAX_SPREAD_PCT` (default 10%)
- Premium per contract = `ask × multiplier`
- Affordability: `premium_per_contract ≤ adjusted_risk_budget`

### Scoring Components (weighted)
| Component | Weight | Description |
|-----------|--------|-------------|
| Liquidity | 0.25 | Bid/ask sizes |
| Spread | 0.20 | Spread % vs. preferred/max |
| Expiry | 0.15 | DTE distance from target (45d) |
| Moneyness | 0.15 | Distance from ATM (1.0) |
| Delta | 0.10 | Distance from target \|delta\| (0.55) |
| IV | 0.10 | Availability & reasonableness (15-60%) |
| Data Quality | 0.05 | GOOD/DEGRADED/INSUFFICIENT |

### Sizing
- `max_contracts = floor(adjusted_risk_budget / premium_per_contract)`
- Capped at `MAX_OPTION_CONTRACTS_PER_PLAN` (default 10)
- `maximum_loss = premium_per_contract × planned_contracts`
- Invariant: `maximum_loss ≤ adjusted_risk_budget`

### Max Loss Semantics
For long options: **maximum loss = premium paid**. No stop-loss modeling; full premium can be lost.

## Comparison & Selection

1. Build equity plan (if eligible)
2. Build option plan (if eligible and options enabled)
3. Compare normalized scores (0-100)
4. Option must beat equity by `OPTION_COMPLEXITY_MARGIN` (default 5 points)
5. Tie → prefer equity (simpler, no expiry/theta, tighter liquidity)
6. If neither eligible → NO_TRADE

### Selection Reasons
- "Option score X beats equity Y by margin" → OPTION
- "Equity score X beats option Y" → STOCK
- "Scores tied, preferring equity" → STOCK
- "Only equity/option eligible" → that instrument
- "No valid instrument plan" → NO_TRADE

## NO_TRADE Reasons
- `RISK_REJECTED`: M4 rejected the thesis
- `MISSING_RISK_BUDGET`: M4 evaluation has no budget
- `INVALID_THESIS`: Malformed or missing direction
- `NO_ELIGIBLE_EQUITY_PLAN`: Equity planning failed
- `OPTIONS_UNAVAILABLE`: Option gateway failure
- `NO_ELIGIBLE_OPTION_CONTRACT`: All contracts filtered out
- `OPTION_DATA_STALE`: Option data too old
- `OPTION_LIQUIDITY_POOR`: All contracts failed liquidity filters
- `OPTION_PREMIUM_TOO_HIGH`: No contract fits in risk budget
- `SHORT_NOT_ALLOWED`: Bearish thesis but short not available
- `SELECTION_SCORE_TOO_LOW`: Best option below minimum threshold
- `RISK_BUDGET_TOO_SMALL`: Budget too small for any instrument
- `DATA_UNAVAILABLE`: Market data missing
- `INTERNAL_VALIDATION_FAILED`: Unexpected error

## M4 Gate (Critical)

```
if risk_evaluation.decision == REJECTED:
    return InstrumentPlan(
        instrument_type=NO_TRADE,
        no_trade_reason="RISK_REJECTED"
    )
    # ZERO option chain requests
```

This enforces that M4 hard rejections are absolute and cannot be overridden by any downstream logic.

## Configuration

```python
# Option filtering
MIN_DTE = 7
TARGET_DTE_MIN = 21
TARGET_DTE_MAX = 60
MAX_DTE = 90

MIN_MONEYNESS_PCT = 0.85
MAX_MONEYNESS_PCT = 1.15
TARGET_ABS_DELTA_MIN = 0.40
TARGET_ABS_DELTA_MAX = 0.75
HARD_ABS_DELTA_MIN = 0.25
HARD_ABS_DELTA_MAX = 0.90

MAX_SPREAD_PCT = 0.10
PREFERRED_SPREAD_PCT = 0.03

MAX_OPTION_CONTRACTS_PER_PLAN = 10

# Scoring
MIN_INSTRUMENT_SCORE = 40.0
OPTION_COMPLEXITY_MARGIN = 5.0

# Data
OPTIONS_ENABLED = True
OPTION_REQUIRE_GREEKS = False
OPTION_REQUIRE_IV = False
```

## Observability

Structured events emitted:
- `instrument_selection_started`
- `equity_alternative_built` / `equity_alternative_rejected`
- `option_chain_requested` / `option_chain_received`
- `option_contract_rejected` (with reason)
- `option_candidate_scored`
- `option_alternative_selected`
- `instrument_comparison_completed`
- `instrument_selected` / `instrument_no_trade`

Rejection summary (not full rejected list):
```python
OptionRejectionSummary(
    total_retrieved=150,
    expired_out_of_range=40,
    spread_too_wide=25,
    premium_too_high=15,
    invalid_quote=5,
    eligible=65
)
```

## Market Closed Behavior

- Market closed + last valid session data → NOT stale failure
- Market open + unexpectedly old quotes → DEGRADED/NO_TRADE
- Uses market clock if available

## Limitations

- No IV rank (no historical IV data)
- No multi-leg strategies
- No stop-loss modeling for options
- Equity shortability not fully implemented
- Option gateway requires explicit API keys (OAuth may not support options endpoints)