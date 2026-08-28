# AlphaCouncil Risk Constitution (v1.0.0)

The Risk Constitution is the absolute authority on capital preservation. It operates completely independently of any AI logic, meaning no amount of AI conviction can override its thresholds.

## Core Mandates
- **Zero LLM Dependency:** The risk module makes zero API calls to language models.
- **Fail-Closed:** Missing data, calculation failures, or invalid prices instantly trigger a rejection.
- **Hard Gates:** Absolute limits that immediately reject a trade.
- **Soft Limits:** Proportional limits that throttle down the risk budget (sizing) without rejecting outright.

## Base Parameters
- **Base Risk Per Trade:** 1.0% of equity
- **Max Position Notional:** 10.0% of equity
- **Max Gross Exposure:** 100.0% of equity
- **Max Net Exposure:** 50.0% of equity
- **Max Open Positions:** 10
- **Max Symbol Concentration:** 5.0% of equity
- **Max Group Concentration:** 20.0% of equity

## Hard Gates (Triggers `REJECTED`)
1. **Kill Switch:** `KILL_SWITCH_ACTIVE` (manual or system-triggered)
2. **M3 NO_TRADE:** `M3_NO_TRADE` (committee refused to trade)
3. **Invalid Thesis:** `INVALID_THESIS` (malformed input)
4. **Poor Data Quality:** `POOR_DATA_QUALITY` (insufficient or stale data)
5. **Low Committee Confidence:** `LOW_COMMITTEE_CONFIDENCE` (< 60% confidence)
6. **Invalid Price:** `INVALID_PRICE` (price <= 0, or spread > 5%)
7. **Daily Loss Limit:** `DAILY_LOSS_LIMIT` (> 3% loss from session-start equity)
8. **Max Drawdown:** `MAX_DRAWDOWN` (> 10% drawdown from peak equity)

## Soft Reductions (Triggers `REDUCED` Size)
1. **Volatility Reduction:** Realized daily volatility > 3% (halves position)
2. **Liquidity Reduction:** Average Daily Dollar Volume < $1M (halves position)
3. **Confidence Reduction:** Committee confidence < 80% (scales down to 75%)
4. **Symbol Concentration:** Existing symbol exposure > 2.5% (halves position)
5. **Gross Exposure:** Portfolio gross > 80% of limit (scales down)
6. **Net Exposure:** Portfolio net > 80% of limit (scales down)
7. **Max Positions:** Open positions >= 8 (halves position)
8. **Group/Sector Concentration:** Group exposure > 15% (halves position)
9. **Correlation Redundancy:** High correlation > 0.70 (halves position)

## Enforcement
The `RiskRulesEngine` evaluates all Hard Gates first. If any fail, evaluation short-circuits to `REJECTED`. If they pass, Soft Limits are evaluated to calculate a multiplicative reduction penalty to pass along to the `PositionSizer`.