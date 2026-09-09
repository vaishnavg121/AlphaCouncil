"""AlphaCouncil FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.memory.api import router as memory_router
from app.orchestration.api import router as council_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    # Startup
    settings = Settings()
    app.state.settings = settings
    yield
    # Shutdown
    # Clean up any resources if needed


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = Settings()

    app = FastAPI(
        title="AlphaCouncil",
        description="Adversarial AI Investment Committee with Deterministic Risk Control",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.trading_mode == "paper" else None,
        redoc_url="/redoc" if settings.trading_mode == "paper" else None,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(memory_router)
    app.include_router(council_router)

    # Root endpoints
    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "name": "AlphaCouncil",
            "description": "Adversarial AI Investment Committee with Deterministic Risk Control",
            "version": "0.1.0",
            "trading_mode": settings.trading_mode,
            "paper_trading": True,
        }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "trading_mode": settings.trading_mode,
            "paper_trading": True,
            "enable_execution": settings.enable_execution,
            "enable_paper_execution": settings.enable_paper_execution,
            "alpaca_live_trade": settings.alpaca_live_trade,
            "services": {
                "backend": "healthy",
                "alpaca": (
                    "not_checked"
                    if settings.alpaca_credentials_configured
                    else "unavailable"
                ),
                "nvidia": (
                    "not_checked"
                    if settings.nvidia_credentials_configured
                    else "not_required"
                ),
            },
        }

    @app.get("/config")
    async def config() -> dict[str, Any]:
        """Sanitized public configuration."""
        return {
            "trading_mode": settings.trading_mode,
            "enable_execution": settings.enable_execution,
            "enable_paper_execution": settings.enable_paper_execution,
            "alpaca_live_trade": settings.alpaca_live_trade,
            "market_data_available": settings.alpaca_credentials_configured,
            "options_data_available": False,  # Will be updated when option gateway is implemented
            "llm_available": settings.nvidia_credentials_configured,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
    )
