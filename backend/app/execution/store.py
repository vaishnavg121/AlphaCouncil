"""Execution Store - Persistence for execution state and crash recovery."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.execution.models import ExecutionAuthorizationState, ExecutionStoreRecord

if TYPE_CHECKING:
    pass


class ExecutionStore:
    """Lightweight SQLite-backed execution store with in-memory support for tests."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = db_path or ":memory:"
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        conn: sqlite3.Connection = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    execution_plan_id TEXT PRIMARY KEY,
                    instrument_plan_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    client_order_id TEXT NOT NULL,
                    authorization_state TEXT NOT NULL,
                    provider_order_id TEXT,
                    provider_status TEXT,
                    created_at TEXT NOT NULL,
                    submitted_at TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_idempotency
                ON executions(idempotency_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executions_client_order
                ON executions(client_order_id)
            """)

    def upsert(self, record: ExecutionStoreRecord) -> None:
        """Insert or update execution record."""
        with self._transaction() as conn:
            auth_state = record.authorization_state
            auth_value: str
            if isinstance(auth_state, ExecutionAuthorizationState):
                auth_value = auth_state.value
            else:
                auth_value = str(auth_state)
            created = (
                record.created_at.isoformat()
                if isinstance(record.created_at, datetime)
                else str(record.created_at)
            )
            submitted = (
                record.submitted_at.isoformat()
                if record.submitted_at and isinstance(record.submitted_at, datetime)
                else (str(record.submitted_at) if record.submitted_at else None)
            )
            updated = (
                record.updated_at.isoformat()
                if isinstance(record.updated_at, datetime)
                else str(record.updated_at)
            )
            conn.execute(
                """
                INSERT INTO executions (
                    execution_plan_id, instrument_plan_id, idempotency_key,
                    client_order_id, authorization_state, provider_order_id,
                    provider_status, created_at, submitted_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_plan_id) DO UPDATE SET
                    instrument_plan_id=excluded.instrument_plan_id,
                    idempotency_key=excluded.idempotency_key,
                    client_order_id=excluded.client_order_id,
                    authorization_state=excluded.authorization_state,
                    provider_order_id=excluded.provider_order_id,
                    provider_status=excluded.provider_status,
                    submitted_at=excluded.submitted_at,
                    updated_at=excluded.updated_at
            """,
                (
                    record.execution_plan_id,
                    record.instrument_plan_id,
                    record.idempotency_key,
                    record.client_order_id,
                    auth_value,
                    record.provider_order_id,
                    record.provider_status,
                    created,
                    submitted,
                    updated,
                ),
            )

    def get_by_idempotency_key(self, idempotency_key: str) -> ExecutionStoreRecord | None:
        """Get record by idempotency key."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE idempotency_key = ?",
                (idempotency_key,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_by_client_order_id(self, client_order_id: str) -> ExecutionStoreRecord | None:
        """Get record by client_order_id."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE client_order_id = ?",
                (client_order_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_by_execution_plan_id(self, execution_plan_id: str) -> ExecutionStoreRecord | None:
        """Get record by execution_plan_id."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_plan_id = ?",
                (execution_plan_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_pending_executions(self) -> list[ExecutionStoreRecord]:
        """Get all executions that are pending provider confirmation."""
        with self._transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM executions
                WHERE authorization_state = 'AUTHORIZED'
                AND (provider_order_id IS NULL OR provider_order_id = '')
                AND updated_at > datetime('now', '-1 hour')
            """).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_active_executions(self) -> list[ExecutionStoreRecord]:
        """Get all non-terminal executions for reconciliation."""
        with self._transaction() as conn:
            rows = conn.execute("""
                SELECT * FROM executions
                WHERE authorization_state = 'AUTHORIZED'
                AND (provider_order_id IS NOT NULL AND provider_order_id != '')
                AND provider_status NOT IN ('FILLED', 'CANCELED', 'EXPIRED', 'REJECTED')
            """).fetchall()
            return [self._row_to_record(row) for row in rows]

    def update_provider_info(
        self,
        execution_plan_id: str,
        provider_order_id: str,
        provider_status: str,
        submitted_at: datetime | None = None,
    ) -> None:
        """Update record with provider order information."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE executions
                SET provider_order_id = ?,
                    provider_status = ?,
                    submitted_at = ?,
                    updated_at = ?
                WHERE execution_plan_id = ?
            """, (
                provider_order_id,
                provider_status,
                submitted_at.isoformat() if submitted_at else datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                execution_plan_id,
            ))

    def update_status(self, execution_plan_id: str, provider_status: str) -> None:
        """Update provider status."""
        with self._transaction() as conn:
            conn.execute("""
                UPDATE executions
                SET provider_status = ?,
                    updated_at = ?
                WHERE execution_plan_id = ?
            """, (
                provider_status,
                datetime.now(UTC).isoformat(),
                execution_plan_id,
            ))

    def _row_to_record(self, row: sqlite3.Row) -> ExecutionStoreRecord:
        """Convert database row to ExecutionStoreRecord."""
        submitted = row["submitted_at"]
        return ExecutionStoreRecord(
            execution_plan_id=row["execution_plan_id"],
            instrument_plan_id=row["instrument_plan_id"],
            idempotency_key=row["idempotency_key"],
            client_order_id=row["client_order_id"],
            authorization_state=ExecutionAuthorizationState(row["authorization_state"]),
            provider_order_id=row["provider_order_id"],
            provider_status=row["provider_status"],
            created_at=datetime.fromisoformat(row["created_at"]),
            submitted_at=datetime.fromisoformat(submitted) if submitted else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


def create_execution_store(db_path: str | Path | None = None) -> ExecutionStore:
    """Factory function to create execution store."""
    return ExecutionStore(db_path)