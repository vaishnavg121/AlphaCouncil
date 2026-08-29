"""Position store - SQLite persistence for managed positions."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from app.positions.models import ExitState, PositionStatus, PositionStoreRecord

if TYPE_CHECKING:
    pass


class PositionStore:
    """Lightweight SQLite-backed position store with in-memory support for tests."""

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
                CREATE TABLE IF NOT EXISTS positions (
                    position_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_execution_id TEXT NOT NULL,
                    entry_order_id TEXT NOT NULL,
                    instrument_plan_id TEXT NOT NULL,
                    entry_timestamp TEXT NOT NULL,
                    entry_price TEXT NOT NULL,
                    initial_quantity TEXT NOT NULL,
                    current_quantity TEXT NOT NULL,
                    current_price TEXT NOT NULL,
                    initial_notional TEXT NOT NULL,
                    current_notional TEXT NOT NULL,
                    risk_budget_at_entry TEXT NOT NULL,
                    constitution_version TEXT NOT NULL,
                    initial_stop_reference TEXT,
                    current_stop_reference TEXT,
                    highest_price_since_entry TEXT,
                    lowest_price_since_entry TEXT,
                    unrealized_pnl TEXT NOT NULL,
                    unrealized_pnl_pct TEXT NOT NULL,
                    realized_pnl TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    mfe TEXT NOT NULL,
                    mae TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_symbol
                ON positions(symbol)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_status
                ON positions(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_positions_entry_execution
                ON positions(entry_execution_id)
            """)

    def upsert(self, record: PositionStoreRecord) -> None:
        """Insert or update position record."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO positions (
                    position_id, symbol, instrument_type, side,
                    entry_execution_id, entry_order_id, instrument_plan_id,
                    entry_timestamp, entry_price, initial_quantity, current_quantity,
                    current_price, initial_notional, current_notional,
                    risk_budget_at_entry, constitution_version,
                    initial_stop_reference, current_stop_reference,
                    highest_price_since_entry, lowest_price_since_entry,
                    unrealized_pnl, unrealized_pnl_pct, realized_pnl,
                    status, exit_state,
                    created_at, updated_at,
                    mfe, mae
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(position_id) DO UPDATE SET
                    symbol=excluded.symbol,
                    instrument_type=excluded.instrument_type,
                    side=excluded.side,
                    entry_execution_id=excluded.entry_execution_id,
                    entry_order_id=excluded.entry_order_id,
                    instrument_plan_id=excluded.instrument_plan_id,
                    entry_timestamp=excluded.entry_timestamp,
                    entry_price=excluded.entry_price,
                    initial_quantity=excluded.initial_quantity,
                    current_quantity=excluded.current_quantity,
                    current_price=excluded.current_price,
                    initial_notional=excluded.initial_notional,
                    current_notional=excluded.current_notional,
                    risk_budget_at_entry=excluded.risk_budget_at_entry,
                    constitution_version=excluded.constitution_version,
                    initial_stop_reference=excluded.initial_stop_reference,
                    current_stop_reference=excluded.current_stop_reference,
                    highest_price_since_entry=excluded.highest_price_since_entry,
                    lowest_price_since_entry=excluded.lowest_price_since_entry,
                    unrealized_pnl=excluded.unrealized_pnl,
                    unrealized_pnl_pct=excluded.unrealized_pnl_pct,
                    realized_pnl=excluded.realized_pnl,
                    status=excluded.status,
                    exit_state=excluded.exit_state,
                    updated_at=excluded.updated_at,
                    mfe=excluded.mfe,
                    mae=excluded.mae
            """,
                (
                    record.position_id,
                    record.symbol,
                    record.instrument_type,
                    record.side,
                    record.entry_execution_id,
                    record.entry_order_id,
                    record.instrument_plan_id,
                    record.entry_timestamp.isoformat(),
                    str(record.entry_price),
                    str(record.initial_quantity),
                    str(record.current_quantity),
                    str(record.current_price),
                    str(record.initial_notional),
                    str(record.current_notional),
                    str(record.risk_budget_at_entry),
                    record.constitution_version,
                    str(record.initial_stop_reference) if record.initial_stop_reference else None,
                    str(record.current_stop_reference) if record.current_stop_reference else None,
                    str(record.highest_price_since_entry) if record.highest_price_since_entry else None,
                    str(record.lowest_price_since_entry) if record.lowest_price_since_entry else None,
                    str(record.unrealized_pnl),
                    str(record.unrealized_pnl_pct),
                    str(record.realized_pnl),
                    record.status,
                    record.exit_state,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    str(record.mfe),
                    str(record.mae),
                ),
            )

    def get_by_position_id(self, position_id: str) -> PositionStoreRecord | None:
        """Get record by position ID."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE position_id = ?",
                (position_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_by_entry_execution_id(self, entry_execution_id: str) -> PositionStoreRecord | None:
        """Get record by entry execution ID."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE entry_execution_id = ?",
                (entry_execution_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_by_entry_order_id(self, entry_order_id: str) -> PositionStoreRecord | None:
        """Get record by entry order ID."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM positions WHERE entry_order_id = ?",
                (entry_order_id,)
            ).fetchone()
            return self._row_to_record(row) if row else None

    def get_open_positions(self) -> list[PositionStoreRecord]:
        """Get all open positions."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status IN (?, ?, ?)",
                (PositionStatus.OPEN.value, PositionStatus.PARTIALLY_EXITED.value, PositionStatus.EXIT_PENDING.value)
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_positions_needing_reconciliation(self) -> list[PositionStoreRecord]:
        """Get positions requiring reconciliation."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM positions WHERE status = ?",
                (PositionStatus.RECONCILIATION_REQUIRED.value,)
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def get_all_positions(self) -> list[PositionStoreRecord]:
        """Get all positions."""
        with self._transaction() as conn:
            rows = conn.execute("SELECT * FROM positions").fetchall()
            return [self._row_to_record(row) for row in rows]

    def update_status(self, position_id: str, status: PositionStatus, exit_state: ExitState | None = None) -> None:
        """Update position status."""
        with self._transaction() as conn:
            if exit_state:
                conn.execute(
                    "UPDATE positions SET status = ?, exit_state = ?, updated_at = ? WHERE position_id = ?",
                    (status.value, exit_state.value, datetime.now(UTC).isoformat(), position_id)
                )
            else:
                conn.execute(
                    "UPDATE positions SET status = ?, updated_at = ? WHERE position_id = ?",
                    (status.value, datetime.now(UTC).isoformat(), position_id)
                )

    def update_quantity(self, position_id: str, current_quantity: Decimal) -> None:
        """Update current quantity after partial fill."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE positions SET current_quantity = ?, updated_at = ? WHERE position_id = ?",
                (str(current_quantity), datetime.now(UTC).isoformat(), position_id)
            )

    def update_current_price(self, position_id: str, current_price: Decimal, current_notional: Decimal,
                             unrealized_pnl: Decimal, unrealized_pnl_pct: Decimal) -> None:
        """Update current market price and PnL."""
        with self._transaction() as conn:
            conn.execute(
                """UPDATE positions SET
                    current_price = ?,
                    current_notional = ?,
                    unrealized_pnl = ?,
                    unrealized_pnl_pct = ?,
                    updated_at = ?
                    WHERE position_id = ?""",
                (str(current_price), str(current_notional), str(unrealized_pnl),
                 str(unrealized_pnl_pct), datetime.now(UTC).isoformat(), position_id)
            )

    def update_watermarks(self, position_id: str, highest: Decimal | None, lowest: Decimal | None,
                          mfe: Decimal, mae: Decimal) -> None:
        """Update high/low watermarks and MFE/MAE."""
        with self._transaction() as conn:
            conn.execute(
                """UPDATE positions SET
                    highest_price_since_entry = ?,
                    lowest_price_since_entry = ?,
                    mfe = ?,
                    mae = ?,
                    updated_at = ?
                    WHERE position_id = ?""",
                (str(highest) if highest else None,
                 str(lowest) if lowest else None,
                 str(mfe), str(mae),
                 datetime.now(UTC).isoformat(), position_id)
            )

    def update_stop_reference(self, position_id: str, stop_reference: Decimal) -> None:
        """Update current stop reference (for trailing stops)."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE positions SET current_stop_reference = ?, updated_at = ? WHERE position_id = ?",
                (str(stop_reference), datetime.now(UTC).isoformat(), position_id)
            )

    def update_realized_pnl(self, position_id: str, realized_pnl: Decimal) -> None:
        """Update realized PnL after partial/full close."""
        with self._transaction() as conn:
            conn.execute(
                "UPDATE positions SET realized_pnl = ?, updated_at = ? WHERE position_id = ?",
                (str(realized_pnl), datetime.now(UTC).isoformat(), position_id)
            )

    def _row_to_record(self, row: sqlite3.Row) -> PositionStoreRecord:
        """Convert database row to PositionStoreRecord."""
        return PositionStoreRecord(
            position_id=row["position_id"],
            symbol=row["symbol"],
            instrument_type=row["instrument_type"],
            side=row["side"],
            entry_execution_id=row["entry_execution_id"],
            entry_order_id=row["entry_order_id"],
            instrument_plan_id=row["instrument_plan_id"],
            entry_timestamp=datetime.fromisoformat(row["entry_timestamp"]),
            entry_price=Decimal(row["entry_price"]),
            initial_quantity=Decimal(row["initial_quantity"]),
            current_quantity=Decimal(row["current_quantity"]),
            current_price=Decimal(row["current_price"]),
            initial_notional=Decimal(row["initial_notional"]),
            current_notional=Decimal(row["current_notional"]),
            risk_budget_at_entry=Decimal(row["risk_budget_at_entry"]),
            constitution_version=row["constitution_version"],
            initial_stop_reference=Decimal(row["initial_stop_reference"]) if row["initial_stop_reference"] else None,
            current_stop_reference=Decimal(row["current_stop_reference"]) if row["current_stop_reference"] else None,
            highest_price_since_entry=Decimal(row["highest_price_since_entry"]) if row["highest_price_since_entry"] else None,
            lowest_price_since_entry=Decimal(row["lowest_price_since_entry"]) if row["lowest_price_since_entry"] else None,
            unrealized_pnl=Decimal(row["unrealized_pnl"]),
            unrealized_pnl_pct=Decimal(row["unrealized_pnl_pct"]),
            realized_pnl=Decimal(row["realized_pnl"]),
            status=PositionStatus(row["status"]),
            exit_state=ExitState(row["exit_state"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            mfe=Decimal(row["mfe"]),
            mae=Decimal(row["mae"]),
        )

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


def create_position_store(db_path: str | Path | None = None) -> PositionStore:
    """Factory function to create position store."""
    return PositionStore(db_path)