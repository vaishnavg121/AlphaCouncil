from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.orchestration import api as orchestration_api


def test_synthetic_demo_run_completes_without_initializing_live_services() -> None:
    orchestration_api._orchestrator = None
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
            assert run["candidates_approved"] == 5
            assert all(item["dry_run"] is True for item in run["candidate_analyses"])
    finally:
        if (
            orchestration_api._orchestrator is not None
            and orchestration_api._orchestrator.memory_service is not None
        ):
            orchestration_api._orchestrator.memory_service.close()
        orchestration_api._orchestrator = None
