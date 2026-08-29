"""Council orchestration API endpoints for M9."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Optional

from app.orchestration.models import (
    CouncilRun,
    CouncilRunRequest,
    CouncilRunResponse,
    CouncilRunStatus,
    CouncilRunEvent,
    CouncilRunEventType,
)
from app.orchestration.service import CouncilOrchestrator, create_council_orchestrator
from app.core.config import Settings

router = APIRouter(prefix="/council", tags=["council"])

# Global orchestrator instance
_orchestrator: Optional[CouncilOrchestrator] = None


def get_orchestrator() -> CouncilOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_council_orchestrator()
    return _orchestrator


@router.post("/run", response_model=CouncilRunResponse)
async def start_council_run(
    request: CouncilRunRequest,
) -> CouncilRunResponse:
    """Start a full council pipeline run."""
    orchestrator = get_orchestrator()
    return await orchestrator.run_council(request)


@router.get("/run/{run_id}", response_model=CouncilRun)
async def get_council_run(
    run_id: str,
) -> CouncilRun:
    """Get council run status and results."""
    orchestrator = get_orchestrator()
    run = orchestrator.get_current_run()
    if not run or run.run_id != run_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/run/{run_id}/events")
async def get_council_run_events(
    run_id: str,
) -> list[CouncilRunEvent]:
    """Get events for a council run (for streaming UI)."""
    # In a real implementation, this would return stored events
    # For now, return empty list
    return []


@router.get("/status")
async def council_status() -> dict:
    """Get council system status."""
    settings = Settings()
    return {
        "status": "ready",
        "trading_mode": settings.trading_mode,
        "paper_trading": True,
        "services": {
            "discovery": "available",
            "committee": "available",
            "risk": "available",
            "instrument": "available",
            "execution": "available",
            "memory": "available",
        },
    }