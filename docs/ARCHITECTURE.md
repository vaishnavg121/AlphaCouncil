# AlphaCouncil Architecture

All components below are **PLANNED**. PRE-M0 implements only configuration and diagnostics.

```text
Alpaca Market Data
        ↓
Deterministic Feature Engine → Universe Scanner → Market Regime Analysis → Quant Analysis
                                                               ↓
                                                     Bull Case / Bear Case
                                                               ↓
                                                        Trade Thesis
                                                               ↓
                                                   Deterministic Risk Engine
                                                               ↓
                                                         Risk Budget
                                                               ↓
                                                  Instrument Selection
                                                    ↙              ↘
                                                Stock/ETF          Option
                                                    ↘              ↙
                                                     Execution Planner
                                                               ↓
                                                      Final Risk Gate
                                                               ↓
                                                    Alpaca PAPER Trade
                                                               ↓
                                      Position Monitoring → Exit Manager → Post-Trade Evaluation
                                                               ↓
                                                        Trading Memory
                                                               ↓
                                                       Future Decisions
```

LLMs will propose structured reasoning, never possess financial authority, and never bypass deterministic risk or execution gates. Research-oriented MCP capabilities will eventually be read-only; execution stays isolated behind the orchestrator, deterministic risk engine, and final execution gate.
