# AlphaCouncil Options Selection (M5)

## Overview

M5 options selection provides deterministic, defined-loss option contract selection for bullish (LONG CALL) and bearish (LONG PUT) theses that have passed M4 risk evaluation.

## Philosophy

**Options are a capital efficiency tool, not a leverage multiplier.**

- Maximum loss = premium paid (defined, bounded)
- No naked short, no multi-leg, no exotic structures
- Conservative filtering favors liquid, near-ATM contracts
- Option must demonstrably beat equity alternative to be selected

## Contract Universe

### Source
Alpaca option chain via `OptionHistoricalDataClient.get_option_chain()`

### Initial Filtering
```python
# Direction-specific
contract_type = ContractType.CALL if thesis_direction == "BULLISH" else ContractType.PUT

# Expiry window
MIN_DTE ≤ DTE ≤ MAX_DTE  # 7-90, target 21-60

# Moneyness
MIN_MONEYNESS ≤ moneyness ≤ MAX_MONEYNESS  # 0.85-1.15
# CALL: spot/strike, PUT: strike/spot

# Delta (if available, not required)
HARD_ABS_DELTA_MIN ≤ |delta| ≤ HARD_ABS_DELTA_MAX  # 0.25-0.90
```

### Moneyness Definitions
- **CALL**: moneyness = `underlying_price / strike_price`
  - ATM: 1.0
  - ITM: > 1.0
  - OTM: < 1.0
- **PUT**: moneyness = `strike_price / underlying_price`
  - ATM: 1.0
  - ITM: > 1.0
  - OTM: < 1.0

### Delta Filtering
- Only applied if Greeks available (`OPTION_REQUIRE_GREEKS=False` by default)
- Target |delta|: 0.55 (near ATM, slightly directional)
- Hard bounds: 0.25 - 0.90
- Target range: 0.40 - 0.75

## Market Data & Quality

### Quote Validation
```python
valid = (
    bid_price > 0 and
    ask_price > 0 and
    ask_price >= bid_price and
    spread_pct ≤ MAX_SPREAD_PCT (10%)
)
```

### Spread Scoring
- ≤ 3% (preferred): 100 points
- 3-10%: linear decay 100→40
- > 10%: 0 points (rejected)

### Data Quality States
- **GOOD**: Valid quote, tight spread, Greeks/IV available
- **DEGRADED**: Valid quote, wider spread (3-5%), some data missing
- **INSUFFICIENT**: No quote, crossed market, or missing critical fields
- **STALE**: Data older than `MAX_DATA_AGE_HOURS` (24h)

## Premium & Affordability

### Premium Calculation
```
premium_per_contract = ask_price × multiplier  # Conservative: use ask
```
Not midpoint! Conservative assumption = no price improvement.

### Affordability Check
```python
if premium_per_contract > adjusted_risk_budget:
    reject  # Can't afford even 1 contract
```

### Contract Quantity
```python
max_contracts = floor(adjusted_risk_budget / premium_per_contract)
planned_contracts = min(max_contracts, MAX_OPTION_CONTRACTS_PER_PLAN)  # default 10
```

## Maximum Loss

**For long options: maximum loss = total premium paid**

```python
maximum_loss = premium_per_contract × planned_contracts
```

**Invariant**: `maximum_loss ≤ adjusted_risk_budget` (always, within 1¢ tolerance)

No stop-loss modeling. Full premium can be lost.

## Scoring

### Component Scores (0-100 each)
| Component | Weight | Key Factors |
|-----------|--------|-------------|
| Liquidity | 0.25 | Bid/ask size depth |
| Spread | 0.20 | Spread % vs preferred/max |
| Expiry | 0.15 | DTE distance from 45d target |
| Moneyness | 0.15 | Distance from ATM (1.0) |
| Delta | 0.10 | \|delta\| distance from 0.55 |
| IV | 0.10 | Available & 15-60% |
| Data Quality | 0.05 | GOOD/DEGRADED/INSUFFICIENT |

### Minimum Score
`MIN_INSTRUMENT_SCORE = 40.0` - below this, contract rejected even if otherwise eligible.

### Option Complexity Margin
Option must beat equity by `OPTION_COMPLEXITY_MARGIN` (5 points) to justify added complexity.

## Contract Ranking (Tie-Breaking)

1. Score descending
2. Spread % ascending
3. |DTE - target| ascending (target 45)
4. \| |delta| - target \| ascending (target 0.55)
5. Contract symbol alphabetical

## Greeks & IV

### Provider-Supplied Only
- No homemade pricing models
- Use Alpaca-supplied Greeks/IV if available
- `OPTION_REQUIRE_GREEKS = False` (not required)
- `OPTION_REQUIRE_IV = False` (not required)

### Validation
```python
# Delta sign convention
if CALL: delta > 0 expected
if PUT: delta < 0 expected

# Gamma ≥ 0 for standard long options
# IV: 0 < iv ≤ 1.0 (reasonable), flag if > 1.0
```

No IV rank, no IV percentile (no historical IV data).

## Fallbacks

### No Greeks Available
- Delta score = 50 (neutral)
- Continue with other scoring components

### No IV Available
- IV score = 50 (neutral)
- Continue with other scoring components

### Option Gateway Unavailable
- Equity alternative still evaluated
- Option rejection: `OPTIONS_UNAVAILABLE`

### All Contracts Filtered
- Option rejection: `NO_ELIGIBLE_OPTION_CONTRACT`
- Equity alternative still evaluated

## Expiry Rules

### DTE Windows
| Window | Range | Treatment |
|--------|-------|-----------|
| Near expiry | DTE < 7 | REJECTED (gamma/theta risk) |
| Target min | 21-60 | PREFERRED |
| Target max | 60-90 | ACCEPTABLE |
| Far expiry | DTE > 90 | REJECTED (liquidity/uncertainty) |

### Market Closed
- Last valid session data → NOT stale
- Use market clock to distinguish

## Maximum Loss Invariant

**CRITICAL**: Every generated option plan must satisfy:

```python
plan.maximum_loss <= risk_budget.adjusted_risk_budget + Decimal("0.01")
```

Verified by:
- Unit test `test_max_loss_invariant`
- Runtime assertion in `OptionSizer.calculate_plan`

## Selection Output

```python
OptionInstrumentPlan(
    contract_symbol="SPY240119C00450000",
    underlying_symbol="SPY",
    option_type=OptionType.CALL,
    expiration_date=date(2024, 1, 19),
    days_to_expiry=21,
    strike_price=Decimal("450"),
    bid_price=Decimal("8.50"),
    ask_price=Decimal("8.70"),
    midpoint=Decimal("8.60"),
    spread=Decimal("0.20"),
    spread_pct=Decimal("0.023"),
    implied_volatility=Decimal("0.18"),
    delta=Decimal("0.58"),
    gamma=Decimal("0.002"),
    theta=Decimal("-0.08"),
    vega=Decimal("0.12"),
    premium_per_contract=Decimal("870.00"),
    multiplier=100,
    planned_contracts=1,
    total_premium=Decimal("870.00"),
    maximum_loss=Decimal("870.00"),
    risk_budget_used=Decimal("870.00"),
    selection_score=Decimal("78.5"),
    selection_reasons=("tight spread", "near target delta", "good liquidity"),
    warnings=("risk_budget_utilization=87.0%",)
)
```

## Rejection Summary

For observability (not full contract list):

```python
OptionRejectionSummary(
    total_retrieved=150,
    expired_out_of_range=40,
    spread_too_wide=25,
    premium_too_high=15,
    invalid_quote=5,
    delta_out_of_range=10,
    moneyness_out_of_range=8,
    zero_bid=3,
    non_tradable=2,
    other=1,
    eligible=41
)
```

## Prohibited

- Naked short calls/puts
- Covered calls
- Cash-secured puts
- Vertical spreads
- Iron condors
- Butterflies
- Straddles/strangles
- Calendar spreads
- Ratio spreads
- Any multi-leg strategy
- Naked short stock (use LONG PUT instead)

## Market Closed Behavior

- Last valid session data → NOT stale failure
- Market open + stale quotes → DEGRADED/NO_TRADE
- Market clock used for distinction

## Limitations

- No IV rank/percentile (no historical IV)
- No stop-loss modeling for options
- No multi-leg strategies
- No early exercise modeling
- No dividend risk modeling
- Option gateway requires API keys (OAuth may not work for options)
- Short stock not fully implemented (use LONG PUT)