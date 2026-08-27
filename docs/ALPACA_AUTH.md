# Alpaca Authentication

AlphaCouncil M0 supports two atomic authentication bundles, always for paper trading:

1. A complete `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` pair supplied locally.
2. The active paper-safe Alpaca CLI profile, preferably through its OAuth access token.

Resolution order is: complete environment API-key pair, active CLI OAuth profile, active CLI API-key pair, then unavailable. A single environment key cannot be combined with a CLI value. Missing or malformed profile files are treated as unavailable; they are not modified.

The profile resolver uses `Path.home()` and standard platform configuration roots, including `~/.config/alpaca`, rather than a user-specific hard-coded path. It reads only the active profile at runtime. Tokens and keys use secret containers, are omitted from representations, and never leave the backend through diagnostics or health responses.

`create_trading_client` only constructs Alpaca SDK clients with `paper=True`. M0's gateway exposes only reads: account, clock, asset lookup, positions, and orders. It has no trade mutation methods.
