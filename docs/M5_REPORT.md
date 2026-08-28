# AlphaCouncil M5 - Deterministic Instrument Selection Report

## M5 STATUS: READY FOR M6

### Recovered Existing Work
M0-M4 were complete and verified at commit `6b6a699`. M5 builds on the M4 Risk Constitution to add instrument selection (stock vs. long options).

### M5 Architecture
- **OptionDataGateway**: Read-only Alpaca option data access (contracts, snapshots, quotes)
- **Normalized Models**: OptionContract, OptionMarketSnapshot, OptionQuote, OptionsGreeks
- **Option Filters**: Expiry (DTE), moneyness, delta, liquidity/spread, affordability
- **Option Scoring**: Multi-factor deterministic scoring (liquidity, spread, expiry, moneyness, delta, IV, data quality)
- **Option Sizing**: Contract quantity from risk budget, max loss = premium × contracts
- **Equity Planner**: Stock/ETF position sizing using M4 provisional stop
- **InstrumentSelectorService**: Orchestrates equity vs. option comparison, selects STOCK/OPTION/NO_TRADE

### M4 Authority Preserved
- M4 REJECTED => immediate M5 NO_TRADE (RISK_REJECTED), zero option chain requests
- M4 RiskBudget treated as immutable ceiling
- planned_max_loss ≤ adjusted_risk_budget (strict invariant)
- planned_notional ≤ max_position_notional
- Soft reductions only reduce risk, never increase

### Supported Instruments
- **STOCK/ETF**: Long or short (subject to shortability)
- **OPTION**: Long CALL (bullish), Long PUT (bearish) only
- **NO_TRADE**: When neither instrument is viable

### Scenarios Tested
**Scenario A — M3 NO_TRADE**: M4 REJECTED => M5 NO_TRADE / RISK_REJECTED (0 option requests)
**Scenario B — Synthetic M4 REDUCED**: Equity plan selected (options unavailable), risk budget respected

### AI Override Test
High-confidence (100%) committee + hard M4 violation => M5 NO_TRADE. AI confidence cannot override M4.

### Safety
- TRADING_MODE=paper, ENABLE_EXECUTION=false, ALPACA_LIVE_TRADE=false
- M4 LLM calls: 0, M5 LLM calls: 0
- Orders submitted: 0, mutations: 0
- No secrets committed, .env untracked

### Tests
- 319 pytest passed (including 49 new M5 tests)
- Ruff: style issues in pre-existing test files only
- Mypy: clean for new M5 modules (pre-existing issues in committee/agents only)

### Git
- Branch: master
- Commit: pending
- .env: untracked, no secrets committed

---

READY FOR M6: YES