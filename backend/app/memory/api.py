"""FastAPI endpoints for M8 Trading Memory (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.memory.models import (
    AgentPerformanceRecord,
    CalibrationSummary,
    DisagreementAnalytics,
    ExitReasonAnalytics,
    HistoricalContext,
    PerformanceSummary,
    SimilarTradeResult,
    TradeRecord,
)
from app.memory.service import TradingMemoryService, create_trading_memory_service

router = APIRouter(prefix="/memory", tags=["trading-memory"])

# Global service instance (initialized on startup)
_memory_service: TradingMemoryService | None = None


def get_memory_service() -> TradingMemoryService:
    """Get or create the memory service singleton."""
    global _memory_service
    if _memory_service is None:
        _memory_service = create_trading_memory_service()
    return _memory_service


def get_memory_service_dep() -> TradingMemoryService:
    """FastAPI dependency for memory service."""
    return get_memory_service()


# =============================================================================
# Request/Response Models
# =============================================================================

class SimilarTradesRequest(BaseModel):
    """Request for similar trades query."""
    direction: str | None = None
    trend_regime: str | None = None
    volatility_bucket: str | None = None
    momentum: float | None = None
    rsi: float | None = None
    committee_confidence: float | None = None
    committee_disagreement: str | None = None
    instrument_type: str | None = None
    k: int = 10


class EvaluatePositionRequest(BaseModel):
    """Request to evaluate a closed position (idempotent)."""
    position_id: str
    committee_result_id: str | None = None
    trade_thesis_id: str | None = None
    risk_evaluation_id: str | None = None
    instrument_plan_id: str | None = None
    entry_execution_id: str | None = None
    exit_execution_id: str | None = None
    underlying_entry_price: float | None = None
    underlying_exit_price: float | None = None


# =============================================================================
# Trade Endpoints
# =============================================================================

@router.get("/trades", response_model=list[TradeRecord])
async def list_trades(
    limit: int = Query(100, ge=1, le=1000),
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[TradeRecord]:
    """Get recent trade records."""
    return service.get_recent_trades(limit)


@router.get("/trades/{trade_id}", response_model=TradeRecord)
async def get_trade(
    trade_id: str,
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> TradeRecord:
    """Get a specific trade record."""
    trade = service.get_trade(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


# =============================================================================
# Performance Endpoints
# =============================================================================

@router.get("/performance", response_model=PerformanceSummary)
async def get_performance(
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> PerformanceSummary:
    """Get comprehensive performance summary."""
    return service.get_performance_summary()


@router.get("/calibration", response_model=CalibrationSummary)
async def get_calibration(
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> CalibrationSummary:
    """Get committee confidence calibration."""
    return service.get_committee_calibration()


@router.post("/calibration/recompute", response_model=CalibrationSummary)
async def recompute_calibration(
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> CalibrationSummary:
    """Recompute calibration from all agent data."""
    return service.recompute_calibration()


# =============================================================================
# Agent Endpoints
# =============================================================================

@router.get("/agents/{agent_name}", response_model=list[AgentPerformanceRecord])
async def get_agent_performance(
    agent_name: str,
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[AgentPerformanceRecord]:
    """Get performance records for a specific agent."""
    if agent_name not in ["QUANT", "BULL", "BEAR", "REGIME"]:
        raise HTTPException(status_code=400, detail="Invalid agent name")
    return service.get_agent_performance(agent_name)


# =============================================================================
# Analytics Endpoints
# =============================================================================

@router.get("/disagreement", response_model=list[DisagreementAnalytics])
async def get_disagreement_stats(
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[DisagreementAnalytics]:
    """Get outcomes by disagreement level."""
    return list(service.get_disagreement_stats())


@router.get("/exits", response_model=list[ExitReasonAnalytics])
async def get_exit_reason_stats(
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[ExitReasonAnalytics]:
    """Get outcomes by exit reason."""
    return list(service.get_exit_reason_stats())


# =============================================================================
# Similar Trades Endpoint
# =============================================================================

@router.post("/similar", response_model=list[SimilarTradeResult])
async def get_similar_trades(
    request: SimilarTradesRequest,
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[SimilarTradeResult]:
    """Find historically similar trades."""
    query = request.model_dump(exclude_none=True)
    k = query.pop("k", 10)
    return service.get_similar_trades(query, k)


@router.get("/similar", response_model=list[SimilarTradeResult])
async def get_similar_trades_get(
    direction: str | None = None,
    trend_regime: str | None = None,
    volatility_bucket: str | None = None,
    momentum: float | None = None,
    rsi: float | None = None,
    committee_confidence: float | None = None,
    committee_disagreement: str | None = None,
    instrument_type: str | None = None,
    k: int = Query(10, ge=1, le=50),
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> list[SimilarTradeResult]:
    """Find historically similar trades (GET version)."""
    query = {
        k: v for k, v in {
            "direction": direction,
            "trend_regime": trend_regime,
            "volatility_bucket": volatility_bucket,
            "momentum": momentum,
            "rsi": rsi,
            "committee_confidence": committee_confidence,
            "committee_disagreement": committee_disagreement,
            "instrument_type": instrument_type,
        }.items() if v is not None
    }
    return service.get_similar_trades(query, k)


# =============================================================================
# Historical Context Endpoint
# =============================================================================

@router.post("/context", response_model=HistoricalContext)
async def get_historical_context(
    request: SimilarTradesRequest,
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> HistoricalContext:
    """Get historical context for a prospective trade."""
    query = request.model_dump(exclude_none=True)
    k = query.pop("k", 10)
    return service.get_historical_context(query, k)


@router.get("/context", response_model=HistoricalContext)
async def get_historical_context_get(
    direction: str | None = None,
    trend_regime: str | None = None,
    volatility_bucket: str | None = None,
    momentum: float | None = None,
    rsi: float | None = None,
    committee_confidence: float | None = None,
    committee_disagreement: str | None = None,
    instrument_type: str | None = None,
    k: int = Query(10, ge=1, le=50),
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> HistoricalContext:
    """Get historical context for a prospective trade (GET version)."""
    query = {
        k: v for k, v in {
            "direction": direction,
            "trend_regime": trend_regime,
            "volatility_bucket": volatility_bucket,
            "momentum": momentum,
            "rsi": rsi,
            "committee_confidence": committee_confidence,
            "committee_disagreement": committee_disagreement,
            "instrument_type": instrument_type,
        }.items() if v is not None
    }
    return service.get_historical_context(query, k)


# =============================================================================
# Evaluation Endpoint (idempotent)
# =============================================================================

@router.post("/evaluate/{position_id}")
async def evaluate_position(
    position_id: str,
    request: EvaluatePositionRequest,
    service: TradingMemoryService = Depends(get_memory_service_dep),
) -> dict:
    """Evaluate a closed position (idempotent).

    Creates or updates the trade record for the given position.
    """

    # Fetch position from position store
    if not service.position_store:
        raise HTTPException(status_code=503, detail="Position store not configured")

    position = service.position_store.get_by_position_id(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    # Convert to ManagedPosition (would need full reconstruction)
    # For now, return not implemented
    raise HTTPException(
        status_code=501,
        detail="Position evaluation requires full M2-M7 record reconstruction. Use internal service."
    )


# =============================================================================
# Health/Info
# =============================================================================

@router.get("/health")
async def memory_health() -> dict:
    """Memory service health check."""
    service = get_memory_service()
    total_trades = len(service.memory_store.get_all_trade_records())
    return {
        "status": "healthy",
        "total_trades": total_trades,
        "paper_trading": True,
        "disclaimer": "All performance data represents PAPER TRADING only. Not real money.",
    }

