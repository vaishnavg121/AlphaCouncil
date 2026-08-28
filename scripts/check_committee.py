"""Real NVIDIA committee diagnostic.

Runs the complete M3 committee pipeline on the top M2 candidate.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution from any current directory without installing a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import Settings
from app.discovery import create_discovery_service
from app.market import AlpacaMarketDataGateway
from app.committee import create_committee_service


def safe_print(text: str) -> None:
    """Print text safely handling Unicode characters."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Replace non-ASCII characters
        safe_text = text.encode('ascii', errors='replace').decode('ascii')
        print(safe_text)


def safe_format(text: str) -> str:
    """Format text for safe printing."""
    return text.encode('ascii', errors='replace').decode('ascii')


def main() -> int:
    settings = Settings()
    safe_print(f"Market data feed: {settings.alpaca_data_feed}")
    safe_print(f"Universe mode: {settings.discovery_universe_mode}")
    safe_print(f"Preliminary K: {settings.discovery_preliminary_k}")
    safe_print(f"Deep analysis K: {settings.discovery_deep_analysis_k}")
    safe_print(f"Final K: {settings.discovery_final_k}")

    try:
        gateway = AlpacaMarketDataGateway.from_settings(settings)
    except Exception as exc:
        safe_print(f"BLOCKED — gateway initialization failed ({type(exc).__name__})")
        return 2

    # Run M2 discovery first
    safe_print("\n=== M2 DISCOVERY ===")
    try:
        discovery_service = create_discovery_service(gateway, settings)
        discovery_result = discovery_service.discover()

        safe_print("Discovery: PASS")
        safe_print(f"Universe: {discovery_result.universe_size} ({discovery_result.universe_mode})")
        safe_print(f"Eligible: {discovery_result.eligible_count}")
        safe_print(f"Rejected: {discovery_result.rejected_count}")
        safe_print(f"Preliminary: {discovery_result.preliminary_count}")
        safe_print(f"Deep analyzed: {discovery_result.deep_analysis_count}")
        safe_print(f"Final candidates: {discovery_result.final_count}")
        safe_print(f"Runtime: {discovery_result.runtime_ms}ms")

        if not discovery_result.candidates:
            safe_print("No candidates found!")
            return 1

        # Take top candidate for committee evaluation
        top_candidate = discovery_result.candidates[0]
        safe_print(f"\nTop candidate: {top_candidate.symbol} (rank #{top_candidate.rank})")
        safe_print(f"Direction: {top_candidate.direction}")
        safe_print(f"Score: {top_candidate.opportunity_score.total}")

    except Exception as exc:
        safe_print(f"BLOCKED — discovery failed ({type(exc).__name__}: {exc})")
        return 2

    # Run M3 committee on top candidate
    safe_print("\n=== M3 COMMITTEE ===")
    try:
        committee_service = create_committee_service(
            gateway,
            settings,
            max_candidates=1,
            agent_concurrency=1,
            enable_rebuttal=True,
        )
        result = committee_service.evaluate_candidate(top_candidate)

        safe_print("\n=== COMMITTEE RESULT ===")
        safe_print(f"Status: PASS")
        safe_print(f"Symbol: {result.candidate_symbol}")
        safe_print(f"Runtime: {result.total_runtime_ms}ms")
        safe_print(f"Total LLM calls: {result.total_llm_calls}")
        safe_print(f"Model: {result.model}")

        # Initial opinions
        safe_print("\n--- INDEPENDENT ROUND ---")
        for op in result.initial_opinions:
            safe_print(f"  {op.agent_role.value}: {op.stance.value} (conf={op.confidence:.2f})")
            safe_print(f"    Thesis: {safe_format(op.thesis[:100])}...")
            safe_print(f"    Evidence: {', '.join(op.supporting_evidence_ids[:3])}...")

        # Disagreement
        if result.disagreement_report:
            safe_print(f"\n--- DISAGREEMENT ---")
            safe_print(f"  Severity: {result.disagreement_report.severity}")
            safe_print(f"  Spread: {result.disagreement_report.stance_spread}")
            if result.disagreement_report.bullish_agents:
                safe_print(f"  Bullish: {', '.join(a.value for a in result.disagreement_report.bullish_agents)}")
            if result.disagreement_report.bearish_agents:
                safe_print(f"  Bearish: {', '.join(a.value for a in result.disagreement_report.bearish_agents)}")

        # Final opinions
        safe_print("\n--- FINAL OPINIONS ---")
        for op in result.final_opinions:
            safe_print(f"  {op.agent_role.value}: {op.stance.value} (conf={op.confidence:.2f})")

        # Decision
        safe_print(f"\n--- DECISION ---")
        safe_print(f"  Decision: {result.decision.decision}")
        if result.decision.direction:
            safe_print(f"  Direction: {result.decision.direction}")
        safe_print(f"  Score: {result.decision.committee_score}")
        safe_print(f"  Confidence: {result.decision.committee_confidence:.2f}")
        if result.decision.no_trade_reason:
            safe_print(f"  NO_TRADE Reason: {result.decision.no_trade_reason}")

        # Trade thesis
        if result.trade_thesis:
            safe_print(f"\n--- TRADE THESIS ---")
            safe_print(f"  Symbol: {result.trade_thesis.symbol}")
            safe_print(f"  Direction: {result.trade_thesis.proposed_direction}")
            safe_print(f"  Confidence: {result.trade_thesis.committee_confidence:.2f}")
            safe_print(f"  Summary: {safe_format(result.trade_thesis.summary)}")

        safe_print(f"\nRuntime: {result.total_runtime_ms}ms")
        safe_print(f"LLM Calls: {result.total_llm_calls}")

    except Exception as exc:
        safe_print(f"FAIL — committee error ({type(exc).__name__}: {exc})")
        import traceback
        traceback.print_exc()
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())