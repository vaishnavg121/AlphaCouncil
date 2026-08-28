# AlphaCouncil Risk Sizing

The `PositionSizer` acts deterministically upon the rulings of the `RiskRulesEngine`. It takes the base risk budget and applies soft penalties to yield a mathematically secure final order size.

## The Formula

1. **Calculate Base Budget:**
   `Base Budget = Equity * BASE_RISK_PER_TRADE (1%)`

2. **Calculate Total Penalty:**
   All soft reduction penalties (Volatility, Liquidity, Confidence, Concentration, Exposure, Correlation) are expressed as decimal factors <= `1.0`. They are multiplicative.
   `Total Reduction = Confidence_Red * Volatility_Red * Liquidity_Red * Concentration_Red * Exposure_Red * Correlation_Red`

3. **Calculate Adjusted Risk Budget:**
   `Adjusted Budget = Base Budget * Total Reduction`
   *Invariant:* Adjusted Budget can never exceed the Base Budget.

4. **Calculate Stop Distance (ATR-Based):**
   AlphaCouncil relies on a volatility-adjusted stop-loss concept.
   `ATR Stop = ATR_14 * ATR_STOP_MULTIPLIER (2.0)`
   The stop is then clamped mathematically to ensure it is never less than 2% or greater than 10% of the reference price.

5. **Determine Target Notional:**
   Given the risk budget and the stop distance, how large can the position be?
   `Stop Distance % = ATR Stop / Reference Price`
   `Target Notional = Adjusted Budget / Stop Distance %`

6. **Apply Absolute Cap:**
   Regardless of tight stop distances, the position can never exceed the portfolio concentration limit.
   `Final Notional = MIN(Target Notional, MAX_POSITION_NOTIONAL_PCT (10%))`

7. **Convert to Shares:**
   `Shares = FLOOR(Final Notional / Reference Price)`

## Fail-Closed Outcomes
If the final calculated shares equal `0` (due to fractional rounding or severe risk penalties driving the budget to negligible levels), the outcome is strictly classified as `REJECTED` under `CALCULATION_FAILURE`. A `REDUCED` flag is only permitted if a non-zero, valid trade can still take place safely.