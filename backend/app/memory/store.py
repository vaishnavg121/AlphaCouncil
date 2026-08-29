"""Trading Memory Store - SQLite persistence for M8."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.memory.models import (
        AgentPerformanceRecord,
        CalibrationSummary,
        ExecutionQualityEvaluation,
        ExitQualityEvaluation,
        InstrumentOutcomeEvaluation,
        RiskOutcomeEvaluation,
        ThesisOutcomeEvaluation,
        TradeOutcome,
        TradeRecord,
    )


class TradingMemoryStore:
    """SQLite-backed trading memory store with in-memory support for tests."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = db_path or ":memory:"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get the store connection shared safely across FastAPI worker threads."""
        return self._conn

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database transactions."""
        with self._lock:
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
            # Trade records table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_records (
                    trade_id TEXT PRIMARY KEY,
                    candidate_id TEXT,
                    committee_result_id TEXT,
                    trade_thesis_id TEXT,
                    risk_evaluation_id TEXT,
                    instrument_plan_id TEXT,
                    entry_execution_id TEXT,
                    position_id TEXT UNIQUE,
                    exit_execution_id TEXT,

                    symbol TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,
                    direction TEXT NOT NULL,

                    discovery_timestamp TEXT,
                    thesis_timestamp TEXT,
                    entry_timestamp TEXT,
                    exit_timestamp TEXT,

                    entry_price TEXT,
                    exit_price TEXT,

                    entry_quantity TEXT,
                    exit_quantity TEXT,

                    entry_notional TEXT,
                    exit_notional TEXT,

                    realized_pnl TEXT,
                    return_pct TEXT,

                    holding_duration_seconds INTEGER,

                    mfe_amount TEXT,
                    mfe_pct TEXT,
                    mfe_r_multiple TEXT,
                    mae_amount TEXT,
                    mae_pct TEXT,
                    mae_r_multiple TEXT,

                    initial_risk_amount TEXT,
                    r_multiple TEXT,
                    risk_budget TEXT,
                    max_position_notional TEXT,
                    initial_stop TEXT,

                    exit_reason_codes TEXT,
                    committee_confidence TEXT,
                    committee_disagreement TEXT,
                    instrument_selection_score TEXT,
                    risk_decision TEXT,
                    constitution_version TEXT,
                    data_quality_flags TEXT,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                )
            """)

            # Trade outcomes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_outcomes (
                    trade_id TEXT PRIMARY KEY,
                    outcome_type TEXT NOT NULL,
                    realized_pnl TEXT,
                    return_pct TEXT,
                    r_multiple TEXT,
                    mfe_pct TEXT,
                    mae_pct TEXT,
                    holding_duration_seconds INTEGER,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Thesis evaluations table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS thesis_evaluations (
                    trade_id TEXT PRIMARY KEY,
                    correctness TEXT NOT NULL,
                    underlying_entry_price TEXT,
                    underlying_exit_price TEXT,
                    underlying_move_pct TEXT,
                    materiality_threshold_pct TEXT NOT NULL,
                    rationale TEXT,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Execution quality evaluations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_quality (
                    trade_id TEXT PRIMARY KEY,
                    entry_planned_price TEXT,
                    entry_actual_price TEXT,
                    entry_slippage_amount TEXT,
                    entry_slippage_pct TEXT,
                    exit_planned_price TEXT,
                    exit_actual_price TEXT,
                    exit_slippage_amount TEXT,
                    exit_slippage_pct TEXT,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Exit quality evaluations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exit_quality (
                    trade_id TEXT PRIMARY KEY,
                    mfe_pct TEXT,
                    realized_return_pct TEXT,
                    captured_profit_ratio TEXT,
                    giveback_from_mfe_pct TEXT,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Risk outcome evaluations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS risk_outcomes (
                    trade_id TEXT PRIMARY KEY,
                    authorized_risk TEXT,
                    realized_loss TEXT,
                    mae_amount TEXT,
                    risk_utilization_pct TEXT,
                    hard_stop_triggered INTEGER DEFAULT 0,
                    kill_switch_triggered INTEGER DEFAULT 0,
                    max_loss_triggered INTEGER DEFAULT 0,
                    m4_reduced_exposure INTEGER DEFAULT 0,
                    reduction_reason TEXT,
                    loss_within_authorized INTEGER,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Instrument outcome evaluations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS instrument_outcomes (
                    trade_id TEXT PRIMARY KEY,
                    instrument_type TEXT NOT NULL,
                    selection_score TEXT,
                    avg_spread_pct TEXT,
                    avg_dollar_volume TEXT,
                    capital_utilization_pct TEXT,
                    risk_utilization_pct TEXT,
                    trade_outcome TEXT,
                    evaluated_at TEXT NOT NULL
                )
            """)

            # Agent performance records
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    stance TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    participated INTEGER DEFAULT 1,
                    abstained INTEGER DEFAULT 0,
                    supporting_evidence_ids TEXT,
                    contradicting_evidence_ids TEXT,
                    direction_correct INTEGER,
                    calibration_target INTEGER,
                    committee_agreement INTEGER,
                    trade_profitable INTEGER,
                    r_multiple TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(trade_id, agent_name)
                )
            """)

            # Calibration snapshots
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    buckets_json TEXT NOT NULL,
                    brier_score TEXT,
                    ece TEXT,
                    min_sample_size INTEGER NOT NULL,
                    overall_insight TEXT NOT NULL,
                    total_samples INTEGER NOT NULL,
                    computed_at TEXT NOT NULL
                )
            """)

            # Similarity query cache (optional, for performance)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS similarity_cache (
                    query_hash TEXT PRIMARY KEY,
                    results_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_symbol ON trade_records(symbol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_entry_time ON trade_records(entry_timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_exit_time ON trade_records(exit_timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_direction ON trade_records(direction)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_records_position ON trade_records(position_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_perf_trade ON agent_performance(trade_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_perf_agent ON agent_performance(agent_name)")

    # =========================================================================
    # Trade Record CRUD
    # =========================================================================

    def upsert_trade_record(self, record: TradeRecord) -> None:
        """Insert or update trade record (idempotent by trade_id)."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO trade_records (
                    trade_id, candidate_id, committee_result_id, trade_thesis_id,
                    risk_evaluation_id, instrument_plan_id, entry_execution_id,
                    position_id, exit_execution_id,
                    symbol, instrument_type, direction,
                    discovery_timestamp, thesis_timestamp, entry_timestamp, exit_timestamp,
                    entry_price, exit_price,
                    entry_quantity, exit_quantity,
                    entry_notional, exit_notional,
                    realized_pnl, return_pct,
                    holding_duration_seconds,
                    mfe_amount, mfe_pct, mfe_r_multiple,
                    mae_amount, mae_pct, mae_r_multiple,
                    initial_risk_amount, r_multiple,
                    risk_budget, max_position_notional, initial_stop,
                    exit_reason_codes, committee_confidence, committee_disagreement,
                    instrument_selection_score, risk_decision, constitution_version,
                    data_quality_flags,
                    created_at, updated_at, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    committee_result_id=excluded.committee_result_id,
                    trade_thesis_id=excluded.trade_thesis_id,
                    risk_evaluation_id=excluded.risk_evaluation_id,
                    instrument_plan_id=excluded.instrument_plan_id,
                    entry_execution_id=excluded.entry_execution_id,
                    position_id=excluded.position_id,
                    exit_execution_id=excluded.exit_execution_id,
                    symbol=excluded.symbol,
                    instrument_type=excluded.instrument_type,
                    direction=excluded.direction,
                    discovery_timestamp=excluded.discovery_timestamp,
                    thesis_timestamp=excluded.thesis_timestamp,
                    entry_timestamp=excluded.entry_timestamp,
                    exit_timestamp=excluded.exit_timestamp,
                    entry_price=excluded.entry_price,
                    exit_price=excluded.exit_price,
                    entry_quantity=excluded.entry_quantity,
                    exit_quantity=excluded.exit_quantity,
                    entry_notional=excluded.entry_notional,
                    exit_notional=excluded.exit_notional,
                    realized_pnl=excluded.realized_pnl,
                    return_pct=excluded.return_pct,
                    holding_duration_seconds=excluded.holding_duration_seconds,
                    mfe_amount=excluded.mfe_amount,
                    mfe_pct=excluded.mfe_pct,
                    mfe_r_multiple=excluded.mfe_r_multiple,
                    mae_amount=excluded.mae_amount,
                    mae_pct=excluded.mae_pct,
                    mae_r_multiple=excluded.mae_r_multiple,
                    initial_risk_amount=excluded.initial_risk_amount,
                    r_multiple=excluded.r_multiple,
                    risk_budget=excluded.risk_budget,
                    max_position_notional=excluded.max_position_notional,
                    initial_stop=excluded.initial_stop,
                    exit_reason_codes=excluded.exit_reason_codes,
                    committee_confidence=excluded.committee_confidence,
                    committee_disagreement=excluded.committee_disagreement,
                    instrument_selection_score=excluded.instrument_selection_score,
                    risk_decision=excluded.risk_decision,
                    constitution_version=excluded.constitution_version,
                    data_quality_flags=excluded.data_quality_flags,
                    updated_at=excluded.updated_at,
                    version=excluded.version
                """,
                (
                    record.trade_id,
                    record.candidate_id,
                    record.committee_result_id,
                    record.trade_thesis_id,
                    record.risk_evaluation_id,
                    record.instrument_plan_id,
                    record.entry_execution_id,
                    record.position_id,
                    record.exit_execution_id,
                    record.symbol,
                    record.instrument_type,
                    record.direction,
                    record.discovery_timestamp.isoformat() if record.discovery_timestamp else None,
                    record.thesis_timestamp.isoformat() if record.thesis_timestamp else None,
                    record.entry_timestamp.isoformat() if record.entry_timestamp else None,
                    record.exit_timestamp.isoformat() if record.exit_timestamp else None,
                    str(record.entry_price) if record.entry_price else None,
                    str(record.exit_price) if record.exit_price else None,
                    str(record.entry_quantity) if record.entry_quantity else None,
                    str(record.exit_quantity) if record.exit_quantity else None,
                    str(record.entry_notional) if record.entry_notional else None,
                    str(record.exit_notional) if record.exit_notional else None,
                    str(record.realized_pnl) if record.realized_pnl else None,
                    str(record.return_pct) if record.return_pct else None,
                    record.holding_duration_seconds,
                    str(record.mfe_amount) if record.mfe_amount else None,
                    str(record.mfe_pct) if record.mfe_pct else None,
                    str(record.mfe_r_multiple) if record.mfe_r_multiple else None,
                    str(record.mae_amount) if record.mae_amount else None,
                    str(record.mae_pct) if record.mae_pct else None,
                    str(record.mae_r_multiple) if record.mae_r_multiple else None,
                    str(record.initial_risk_amount) if record.initial_risk_amount else None,
                    str(record.r_multiple) if record.r_multiple else None,
                    str(record.risk_budget) if record.risk_budget else None,
                    str(record.max_position_notional) if record.max_position_notional else None,
                    str(record.initial_stop) if record.initial_stop else None,
                    ",".join(record.exit_reason_codes) if record.exit_reason_codes else "",
                    str(record.committee_confidence) if record.committee_confidence else None,
                    record.committee_disagreement,
                    str(record.instrument_selection_score) if record.instrument_selection_score else None,
                    record.risk_decision,
                    record.constitution_version,
                    ",".join(record.data_quality_flags) if record.data_quality_flags else "",
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.version,
                ),
            )

    def get_trade_record(self, trade_id: str) -> TradeRecord | None:
        """Get trade record by ID."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM trade_records WHERE trade_id = ?",
                (trade_id,)
            ).fetchone()
            return self._row_to_trade_record(row) if row else None

    def get_trade_record_by_position_id(self, position_id: str) -> TradeRecord | None:
        """Get trade record by position ID (for idempotent evaluation)."""
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM trade_records WHERE position_id = ?",
                (position_id,)
            ).fetchone()
            return self._row_to_trade_record(row) if row else None

    def get_recent_trades(self, limit: int = 100) -> list[TradeRecord]:
        """Get most recent trade records."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_records ORDER BY entry_timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [self._row_to_trade_record(row) for row in rows]

    def get_all_trade_records(self) -> list[TradeRecord]:
        """Get all trade records."""
        with self._transaction() as conn:
            rows = conn.execute("SELECT * FROM trade_records").fetchall()
            return [self._row_to_trade_record(row) for row in rows]

    def _row_to_trade_record(self, row: sqlite3.Row) -> TradeRecord:
        """Convert database row to TradeRecord."""
        from app.memory.models import TradeRecord
        return TradeRecord(
            trade_id=row["trade_id"],
            candidate_id=row["candidate_id"],
            committee_result_id=row["committee_result_id"],
            trade_thesis_id=row["trade_thesis_id"],
            risk_evaluation_id=row["risk_evaluation_id"],
            instrument_plan_id=row["instrument_plan_id"],
            entry_execution_id=row["entry_execution_id"],
            position_id=row["position_id"],
            exit_execution_id=row["exit_execution_id"],
            symbol=row["symbol"],
            instrument_type=row["instrument_type"],
            direction=row["direction"],
            discovery_timestamp=datetime.fromisoformat(row["discovery_timestamp"]) if row["discovery_timestamp"] else None,
            thesis_timestamp=datetime.fromisoformat(row["thesis_timestamp"]) if row["thesis_timestamp"] else None,
            entry_timestamp=datetime.fromisoformat(row["entry_timestamp"]) if row["entry_timestamp"] else None,
            exit_timestamp=datetime.fromisoformat(row["exit_timestamp"]) if row["exit_timestamp"] else None,
            entry_price=Decimal(row["entry_price"]) if row["entry_price"] else None,
            exit_price=Decimal(row["exit_price"]) if row["exit_price"] else None,
            entry_quantity=Decimal(row["entry_quantity"]) if row["entry_quantity"] else None,
            exit_quantity=Decimal(row["exit_quantity"]) if row["exit_quantity"] else None,
            entry_notional=Decimal(row["entry_notional"]) if row["entry_notional"] else None,
            exit_notional=Decimal(row["exit_notional"]) if row["exit_notional"] else None,
            realized_pnl=Decimal(row["realized_pnl"]) if row["realized_pnl"] else None,
            return_pct=Decimal(row["return_pct"]) if row["return_pct"] else None,
            holding_duration_seconds=row["holding_duration_seconds"],
            mfe_amount=Decimal(row["mfe_amount"]) if row["mfe_amount"] else None,
            mfe_pct=Decimal(row["mfe_pct"]) if row["mfe_pct"] else None,
            mfe_r_multiple=Decimal(row["mfe_r_multiple"]) if row["mfe_r_multiple"] else None,
            mae_amount=Decimal(row["mae_amount"]) if row["mae_amount"] else None,
            mae_pct=Decimal(row["mae_pct"]) if row["mae_pct"] else None,
            mae_r_multiple=Decimal(row["mae_r_multiple"]) if row["mae_r_multiple"] else None,
            initial_risk_amount=Decimal(row["initial_risk_amount"]) if row["initial_risk_amount"] else None,
            r_multiple=Decimal(row["r_multiple"]) if row["r_multiple"] else None,
            risk_budget=Decimal(row["risk_budget"]) if row["risk_budget"] else None,
            max_position_notional=Decimal(row["max_position_notional"]) if row["max_position_notional"] else None,
            initial_stop=Decimal(row["initial_stop"]) if row["initial_stop"] else None,
            exit_reason_codes=tuple(row["exit_reason_codes"].split(",")) if row["exit_reason_codes"] else (),
            committee_confidence=Decimal(row["committee_confidence"]) if row["committee_confidence"] else None,
            committee_disagreement=row["committee_disagreement"],
            instrument_selection_score=Decimal(row["instrument_selection_score"]) if row["instrument_selection_score"] else None,
            risk_decision=row["risk_decision"],
            constitution_version=row["constitution_version"],
            data_quality_flags=tuple(row["data_quality_flags"].split(",")) if row["data_quality_flags"] else (),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            version=row["version"],
        )

    # =========================================================================
    # Trade Outcome
    # =========================================================================

    def upsert_trade_outcome(self, outcome: TradeOutcome) -> None:
        """Insert or update trade outcome."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO trade_outcomes (
                    trade_id, outcome_type, realized_pnl, return_pct,
                    r_multiple, mfe_pct, mae_pct, holding_duration_seconds,
                    evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    outcome_type=excluded.outcome_type,
                    realized_pnl=excluded.realized_pnl,
                    return_pct=excluded.return_pct,
                    r_multiple=excluded.r_multiple,
                    mfe_pct=excluded.mfe_pct,
                    mae_pct=excluded.mae_pct,
                    holding_duration_seconds=excluded.holding_duration_seconds,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    outcome.trade_id,
                    outcome.outcome_type.value,
                    str(outcome.realized_pnl) if outcome.realized_pnl else None,
                    str(outcome.return_pct) if outcome.return_pct else None,
                    str(outcome.r_multiple) if outcome.r_multiple else None,
                    str(outcome.mfe_pct) if outcome.mfe_pct else None,
                    str(outcome.mae_pct) if outcome.mae_pct else None,
                    outcome.holding_duration_seconds,
                    outcome.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Thesis Evaluation
    # =========================================================================

    def upsert_thesis_evaluation(self, eval: ThesisOutcomeEvaluation) -> None:
        """Insert or update thesis evaluation."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO thesis_evaluations (
                    trade_id, correctness, underlying_entry_price,
                    underlying_exit_price, underlying_move_pct,
                    materiality_threshold_pct, rationale, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    correctness=excluded.correctness,
                    underlying_entry_price=excluded.underlying_entry_price,
                    underlying_exit_price=excluded.underlying_exit_price,
                    underlying_move_pct=excluded.underlying_move_pct,
                    materiality_threshold_pct=excluded.materiality_threshold_pct,
                    rationale=excluded.rationale,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    eval.trade_id,
                    eval.correctness.value,
                    str(eval.underlying_entry_price) if eval.underlying_entry_price else None,
                    str(eval.underlying_exit_price) if eval.underlying_exit_price else None,
                    str(eval.underlying_move_pct) if eval.underlying_move_pct else None,
                    str(eval.materiality_threshold_pct),
                    eval.rationale,
                    eval.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Execution Quality
    # =========================================================================

    def upsert_execution_quality(self, eval: ExecutionQualityEvaluation) -> None:
        """Insert or update execution quality evaluation."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO execution_quality (
                    trade_id, entry_planned_price, entry_actual_price,
                    entry_slippage_amount, entry_slippage_pct,
                    exit_planned_price, exit_actual_price,
                    exit_slippage_amount, exit_slippage_pct,
                    evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    entry_planned_price=excluded.entry_planned_price,
                    entry_actual_price=excluded.entry_actual_price,
                    entry_slippage_amount=excluded.entry_slippage_amount,
                    entry_slippage_pct=excluded.entry_slippage_pct,
                    exit_planned_price=excluded.exit_planned_price,
                    exit_actual_price=excluded.exit_actual_price,
                    exit_slippage_amount=excluded.exit_slippage_amount,
                    exit_slippage_pct=excluded.exit_slippage_pct,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    eval.trade_id,
                    str(eval.entry_planned_price) if eval.entry_planned_price else None,
                    str(eval.entry_actual_price) if eval.entry_actual_price else None,
                    str(eval.entry_slippage_amount) if eval.entry_slippage_amount else None,
                    str(eval.entry_slippage_pct) if eval.entry_slippage_pct else None,
                    str(eval.exit_planned_price) if eval.exit_planned_price else None,
                    str(eval.exit_actual_price) if eval.exit_actual_price else None,
                    str(eval.exit_slippage_amount) if eval.exit_slippage_amount else None,
                    str(eval.exit_slippage_pct) if eval.exit_slippage_pct else None,
                    eval.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Exit Quality
    # =========================================================================

    def upsert_exit_quality(self, eval: ExitQualityEvaluation) -> None:
        """Insert or update exit quality evaluation."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO exit_quality (
                    trade_id, mfe_pct, realized_return_pct,
                    captured_profit_ratio, giveback_from_mfe_pct,
                    evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    mfe_pct=excluded.mfe_pct,
                    realized_return_pct=excluded.realized_return_pct,
                    captured_profit_ratio=excluded.captured_profit_ratio,
                    giveback_from_mfe_pct=excluded.giveback_from_mfe_pct,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    eval.trade_id,
                    str(eval.mfe_pct) if eval.mfe_pct else None,
                    str(eval.realized_return_pct) if eval.realized_return_pct else None,
                    str(eval.captured_profit_ratio) if eval.captured_profit_ratio else None,
                    str(eval.giveback_from_mfe_pct) if eval.giveback_from_mfe_pct else None,
                    eval.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Risk Outcome
    # =========================================================================

    def upsert_risk_outcome(self, eval: RiskOutcomeEvaluation) -> None:
        """Insert or update risk outcome evaluation."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO risk_outcomes (
                    trade_id, authorized_risk, realized_loss, mae_amount,
                    risk_utilization_pct, hard_stop_triggered, kill_switch_triggered,
                    max_loss_triggered, m4_reduced_exposure, reduction_reason,
                    loss_within_authorized, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    authorized_risk=excluded.authorized_risk,
                    realized_loss=excluded.realized_loss,
                    mae_amount=excluded.mae_amount,
                    risk_utilization_pct=excluded.risk_utilization_pct,
                    hard_stop_triggered=excluded.hard_stop_triggered,
                    kill_switch_triggered=excluded.kill_switch_triggered,
                    max_loss_triggered=excluded.max_loss_triggered,
                    m4_reduced_exposure=excluded.m4_reduced_exposure,
                    reduction_reason=excluded.reduction_reason,
                    loss_within_authorized=excluded.loss_within_authorized,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    eval.trade_id,
                    str(eval.authorized_risk) if eval.authorized_risk else None,
                    str(eval.realized_loss) if eval.realized_loss else None,
                    str(eval.mae_amount) if eval.mae_amount else None,
                    str(eval.risk_utilization_pct) if eval.risk_utilization_pct else None,
                    1 if eval.hard_stop_triggered else 0,
                    1 if eval.kill_switch_triggered else 0,
                    1 if eval.max_loss_triggered else 0,
                    1 if eval.m4_reduced_exposure else 0,
                    eval.reduction_reason,
                    1 if eval.loss_within_authorized else 0 if eval.loss_within_authorized is not None else None,
                    eval.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Instrument Outcome
    # =========================================================================

    def upsert_instrument_outcome(self, eval: InstrumentOutcomeEvaluation) -> None:
        """Insert or update instrument outcome evaluation."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO instrument_outcomes (
                    trade_id, instrument_type, selection_score,
                    avg_spread_pct, avg_dollar_volume,
                    capital_utilization_pct, risk_utilization_pct,
                    trade_outcome, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    instrument_type=excluded.instrument_type,
                    selection_score=excluded.selection_score,
                    avg_spread_pct=excluded.avg_spread_pct,
                    avg_dollar_volume=excluded.avg_dollar_volume,
                    capital_utilization_pct=excluded.capital_utilization_pct,
                    risk_utilization_pct=excluded.risk_utilization_pct,
                    trade_outcome=excluded.trade_outcome,
                    evaluated_at=excluded.evaluated_at
                """,
                (
                    eval.trade_id,
                    eval.instrument_type,
                    str(eval.selection_score) if eval.selection_score else None,
                    str(eval.avg_spread_pct) if eval.avg_spread_pct else None,
                    str(eval.avg_dollar_volume) if eval.avg_dollar_volume else None,
                    str(eval.capital_utilization_pct) if eval.capital_utilization_pct else None,
                    str(eval.risk_utilization_pct) if eval.risk_utilization_pct else None,
                    eval.trade_outcome.value if eval.trade_outcome else None,
                    eval.evaluated_at.isoformat(),
                ),
            )

    # =========================================================================
    # Agent Performance
    # =========================================================================

    def upsert_agent_performance(self, record: AgentPerformanceRecord) -> None:
        """Insert or update agent performance record."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO agent_performance (
                    trade_id, agent_name, stance, confidence,
                    participated, abstained, supporting_evidence_ids,
                    contradicting_evidence_ids, direction_correct,
                    calibration_target, committee_agreement,
                    trade_profitable, r_multiple, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id, agent_name) DO UPDATE SET
                    stance=excluded.stance,
                    confidence=excluded.confidence,
                    participated=excluded.participated,
                    abstained=excluded.abstained,
                    supporting_evidence_ids=excluded.supporting_evidence_ids,
                    contradicting_evidence_ids=excluded.contradicting_evidence_ids,
                    direction_correct=excluded.direction_correct,
                    calibration_target=excluded.calibration_target,
                    committee_agreement=excluded.committee_agreement,
                    trade_profitable=excluded.trade_profitable,
                    r_multiple=excluded.r_multiple,
                    created_at=excluded.created_at
                """,
                (
                    record.trade_id,
                    record.agent_name,
                    record.stance.value,
                    str(record.confidence),
                    1 if record.participated else 0,
                    1 if record.abstained else 0,
                    ",".join(record.supporting_evidence_ids) if record.supporting_evidence_ids else "",
                    ",".join(record.contradicting_evidence_ids) if record.contradicting_evidence_ids else "",
                    1 if record.direction_correct else 0 if record.direction_correct is not None else None,
                    1 if record.calibration_target else 0 if record.calibration_target is not None else None,
                    1 if record.committee_agreement else 0 if record.committee_agreement is not None else None,
                    1 if record.trade_profitable else 0 if record.trade_profitable is not None else None,
                    str(record.r_multiple) if record.r_multiple else None,
                    record.created_at.isoformat(),
                ),
            )

    def get_agent_performance(self, trade_id: str) -> list[AgentPerformanceRecord]:
        """Get all agent performance records for a trade."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_performance WHERE trade_id = ?",
                (trade_id,)
            ).fetchall()
            return [self._row_to_agent_performance(row) for row in rows]

    def get_agent_history(self, agent_name: str) -> list[AgentPerformanceRecord]:
        """Get all performance records for an agent."""
        with self._transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_performance WHERE agent_name = ? ORDER BY created_at",
                (agent_name,)
            ).fetchall()
            return [self._row_to_agent_performance(row) for row in rows]

    def _row_to_agent_performance(self, row: sqlite3.Row) -> AgentPerformanceRecord:
        """Convert database row to AgentPerformanceRecord."""
        from app.memory.models import AgentPerformanceRecord, AgentStance
        return AgentPerformanceRecord(
            trade_id=row["trade_id"],
            agent_name=row["agent_name"],
            stance=AgentStance(row["stance"]),
            confidence=Decimal(row["confidence"]),
            participated=bool(row["participated"]),
            abstained=bool(row["abstained"]),
            supporting_evidence_ids=tuple(row["supporting_evidence_ids"].split(",")) if row["supporting_evidence_ids"] else (),
            contradicting_evidence_ids=tuple(row["contradicting_evidence_ids"].split(",")) if row["contradicting_evidence_ids"] else (),
            direction_correct=bool(row["direction_correct"]) if row["direction_correct"] is not None else None,
            calibration_target=row["calibration_target"] if row["calibration_target"] is not None else None,
            committee_agreement=bool(row["committee_agreement"]) if row["committee_agreement"] is not None else None,
            trade_profitable=bool(row["trade_profitable"]) if row["trade_profitable"] is not None else None,
            r_multiple=Decimal(row["r_multiple"]) if row["r_multiple"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # =========================================================================
    # Calibration
    # =========================================================================

    def save_calibration_snapshot(self, calibration: CalibrationSummary) -> None:
        """Save calibration snapshot."""
        import json
        with self._transaction() as conn:
            buckets_json = json.dumps([
                {
                    "bucket_low": str(b.bucket_low),
                    "bucket_high": str(b.bucket_high),
                    "sample_count": b.sample_count,
                    "mean_predicted_confidence": str(b.mean_predicted_confidence) if b.mean_predicted_confidence else None,
                    "observed_success_rate": str(b.observed_success_rate) if b.observed_success_rate else None,
                    "calibration_gap": str(b.calibration_gap) if b.calibration_gap else None,
                }
                for b in calibration.buckets
            ])
            conn.execute(
                """
                INSERT INTO calibration_snapshots (
                    buckets_json, brier_score, ece, min_sample_size,
                    overall_insight, total_samples, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    buckets_json,
                    str(calibration.brier_score) if calibration.brier_score else None,
                    str(calibration.ece) if calibration.ece else None,
                    calibration.min_sample_size,
                    calibration.overall_insight.value,
                    calibration.total_samples,
                    calibration.computed_at.isoformat(),
                ),
            )

    def get_latest_calibration(self) -> CalibrationSummary | None:
        """Get latest calibration snapshot."""
        import json
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM calibration_snapshots ORDER BY computed_at DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            buckets_data = json.loads(row["buckets_json"])
            buckets = []
            for b in buckets_data:
                from app.memory.models import CalibrationBucket
                buckets.append(CalibrationBucket(
                    bucket_low=Decimal(b["bucket_low"]),
                    bucket_high=Decimal(b["bucket_high"]),
                    sample_count=b["sample_count"],
                    mean_predicted_confidence=Decimal(b["mean_predicted_confidence"]) if b["mean_predicted_confidence"] else None,
                    observed_success_rate=Decimal(b["observed_success_rate"]) if b["observed_success_rate"] else None,
                    calibration_gap=Decimal(b["calibration_gap"]) if b["calibration_gap"] else None,
                ))
            from app.memory.models import CalibrationInsight, CalibrationSummary
            return CalibrationSummary(
                buckets=tuple(buckets),
                brier_score=Decimal(row["brier_score"]) if row["brier_score"] else None,
                ece=Decimal(row["ece"]) if row["ece"] else None,
                min_sample_size=row["min_sample_size"],
                overall_insight=CalibrationInsight(row["overall_insight"]),
                total_samples=row["total_samples"],
                computed_at=datetime.fromisoformat(row["computed_at"]),
            )

    # =========================================================================
    # Utility
    # =========================================================================

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            self._conn.close()


def create_trading_memory_store(db_path: str | Path | None = None) -> TradingMemoryStore:
    """Factory function to create trading memory store."""
    return TradingMemoryStore(db_path)
