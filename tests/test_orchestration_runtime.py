from __future__ import annotations

from typing import Any, cast

from fastapi.testclient import TestClient

from app.alpaca.gateway import AlpacaGateway
from app.main import create_app
from app.orchestration import api as orchestration_api
from app.orchestration.service import CouncilOrchestrator
from app.positions.store import PositionStore


class FailIfTouchedGateway:
    """Records any attempted broker interaction during Demo Mode."""

    def __init__(self) -> None:
        self.touched = False

    def __getattr__(self, name: str) -> Any:
        self.touched = True
        raise AssertionError(f"Demo Mode attempted Alpaca access: {name}")


def test_synthetic_demo_run_completes_without_initializing_live_services() -> None:
    gateway = FailIfTouchedGateway()
    position_store = PositionStore()
    orchestration_api._orchestrator = CouncilOrchestrator(
        alpaca_gateway=cast(AlpacaGateway, gateway),
        position_store=position_store,
    )
    try:
        with TestClient(create_app()) as client:
            response = client.post(
                "/council/run",
                json={
                    "max_candidates": 5,
                    "demo_mode": True,
                    "universe_mode": "curated",
                },
            )
            assert response.status_code == 200
            started = response.json()
            assert started["status"] == "COMPLETE"

            run_response = client.get(f"/council/run/{started['run_id']}")
            assert run_response.status_code == 200
            run = run_response.json()
            assert run["demo_mode"] is True
            assert run["candidates_analyzed"] == 5
            assert run["candidates_approved"] == 4
            assert run["candidates_rejected"] == 1

            opportunities = run["candidate_set"]["candidates"]
            analyses = run["candidate_analyses"]
            opportunity_identity = [
                (item["candidate_id"], item["symbol"]) for item in opportunities
            ]
            analysis_identity = [
                (item["candidate_id"], item["symbol"]) for item in analyses
            ]
            assert opportunity_identity == analysis_identity

            candidates_response = client.get(
                f"/council/run/{started['run_id']}/candidates"
            )
            assert candidates_response.status_code == 200
            assert [
                (item["candidate_id"], item["symbol"])
                for item in candidates_response.json()
            ] == opportunity_identity

            current_response = client.get("/council/current")
            assert current_response.status_code == 200
            assert current_response.json()["run_id"] == started["run_id"]

            traced = next(item for item in analyses if item["symbol"] == "SPY")
            assert traced["opportunity"]["candidate_id"] == traced["candidate_id"]
            assert traced["committee_result"]["candidate_symbol"] == "SPY"
            assert traced["risk_evaluation"]["symbol"] == "SPY"
            assert traced["instrument_plan"]["symbol"] == "SPY"
            assert traced["execution_plan"]["symbol"] == "SPY"
            assert (
                traced["execution_plan"]["instrument_plan_id"]
                == traced["instrument_plan"]["plan_id"]
            )

            rejected = next(item for item in analyses if item["symbol"] == "AAPL")
            assert rejected["risk_evaluation"]["decision"] == "REJECTED"
            assert rejected["instrument_plan"] is None
            assert rejected["execution_plan"] is None
            assert rejected["stop_reason_codes"] == ["M4_RISK_REJECTED"]

            no_trade = next(item for item in analyses if item["symbol"] == "TSLA")
            assert no_trade["instrument_plan"]["instrument_type"] == "NO_TRADE"
            assert no_trade["execution_plan"] is None
            assert no_trade["stop_reason_codes"] == ["INSTRUMENT_NO_TRADE"]

            assert all(item["dry_run"] is True for item in analyses)
            assert all(item["execution_status"] == "NOT_EXECUTED" for item in analyses)
            assert not any(item["execution_authorized"] for item in analyses)
            assert gateway.touched is False
            assert position_store.get_all_positions() == []
            assert orchestration_api._orchestrator.memory_service is not None
            assert orchestration_api._orchestrator.memory_service.get_recent_trades() == []
    finally:
        if (
            orchestration_api._orchestrator is not None
            and orchestration_api._orchestrator.memory_service is not None
        ):
            orchestration_api._orchestrator.memory_service.close()
        position_store.close()
        orchestration_api._orchestrator = None
