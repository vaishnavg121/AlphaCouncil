from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.main import create_app
from app.memory import api as memory_api
from app.memory.store import TradingMemoryStore


def test_in_memory_store_schema_is_shared_across_threads() -> None:
    store = TradingMemoryStore()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            trades = executor.submit(store.get_recent_trades, 20).result()
        assert trades == []
    finally:
        store.close()


def test_empty_memory_dashboard_endpoints_are_available() -> None:
    memory_api._memory_service = None
    try:
        with TestClient(create_app()) as client:
            assert client.get("/memory/trades", params={"limit": 20}).status_code == 200
            assert client.get("/memory/performance").status_code == 200
            response = client.post(
                "/memory/context",
                json={"direction": "LONG", "instrument_type": "STOCK"},
            )
            assert response.status_code == 200
    finally:
        if memory_api._memory_service is not None:
            memory_api._memory_service.close()
        memory_api._memory_service = None
