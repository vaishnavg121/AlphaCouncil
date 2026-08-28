"""Real Alpaca opportunity discovery diagnostic.

Read-only diagnostic that runs the complete M2 discovery pipeline
on a curated liquid universe.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings
from app.discovery import create_discovery_service
from app.market import AlpacaMarketDataGateway


def main() -> int:
    settings = Settings()
    print(f"Market data feed: {settings.alpaca_data_feed}")
    print(f"Universe mode: {settings.discovery_universe_mode}")
    print(f"Preliminary K: {settings.discovery_preliminary_k}")
    print(f"Deep analysis K: {settings.discovery_deep_analysis_k}")
    print(f"Final K: {settings.discovery_final_k}")

    try:
        gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        print(f"BLOCKED — gateway initialization failed ({type(exc).__name__})")
        return 2

    try:
        service = create_discovery_service(gateway, settings)
        result = service.discover()

        print("\n=== DISCOVERY RESULT ===")
        print("Status: PASS")
        print(f"Generated: {result.generated_at}")
        print(f"Universe: {result.universe_size} ({result.universe_mode})")
        print(f"Eligible: {result.eligible_count}")
        print(f"Rejected: {result.rejected_count}")
        print(f"Preliminary: {result.preliminary_count}")
        print(f"Deep analyzed: {result.deep_analysis_count}")
        print(f"Final candidates: {result.final_count}")
        print(f"Runtime: {result.runtime_ms}ms")

        if result.rejections:
            print(f"\nRejections ({len(result.rejections)}):")
            for r in result.rejections[:10]:  # Show first 10
                print(f"  {r.symbol}: {r.reason} - {r.message}")
            if len(result.rejections) > 10:
                print(f"  ... and {len(result.rejections) - 10} more")

        print(f"\n=== FINAL CANDIDATES ({len(result.candidates)}) ===")
        for c in result.candidates:
            print(f"\n#{c.rank} {c.symbol}")
            print(f"  Direction: {c.direction}")
            print(f"  Score: {c.opportunity_score.total} (M:{c.opportunity_score.momentum} T:{c.opportunity_score.trend} V:{c.opportunity_score.volume} Vol:{c.opportunity_score.volatility} MR:{c.opportunity_score.mean_reversion} L:{c.opportunity_score.liquidity} Q:{c.opportunity_score.quality})")
            if c.opportunity_score.reasons:
                print("  Reasons:")
                for reason in c.opportunity_score.reasons[:4]:
                    print(f"    - {reason}")
            if c.warnings:
                print("  Warnings:")
                for w in c.warnings:
                    print(f"    - {w}")
            if c.data_quality_status:
                print(f"  Data Quality: {c.data_quality_status}")

    except Exception as exc:
        print(f"FAIL — discovery error ({type(exc).__name__}: {exc})")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())