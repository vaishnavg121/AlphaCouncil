# Safety Policy

AlphaCouncil is **paper-trading only** during hackathon development. `ALPACA_LIVE_TRADE` defaults to `false`, `TRADING_MODE` must be `paper`, and `ENABLE_EXECUTION` defaults to `false`. A live-trading configuration fails closed during settings validation.

LLMs may eventually propose decisions, but they are not financial authority. Deterministic code will calculate risk, sizing, constraints, and validity. Every future order must pass a final deterministic gate and use a unique `client_order_id` for idempotency protection.

Credentials remain backend-only: no frontend code may receive `ALPACA_SECRET_KEY` or `NVIDIA_API_KEY`. MCP access will be least-privilege; research agents have no execution authority. Arbitrary LLM shell execution is prohibited. Direct access to close-all, cancel-all, option exercise, or similar destructive brokerage operations must never be available to an unconstrained model.

Kill-switch support, controlled paper orders, and order lifecycle behavior are deliberately deferred to future milestones.
