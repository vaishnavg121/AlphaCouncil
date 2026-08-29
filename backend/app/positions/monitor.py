"""Position monitoring service for M7."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.alpaca.gateway import AlpacaGateway
from app.market.gateway import MarketDataGateway
from app.positions import PositionStoreRecord
from app.positions.metrics import ExitRulesEngine, PositionMetrics
from app.positions.models import (
    ExitDecision,
    ExitDecisionType,
    ExitState,
    ManagedPosition,
    PositionReconciliationResult,
    PositionSnapshot,
    PositionStatus,
)
from app.positions.reconciliation import PositionReconciler
from app.positions.store import PositionStore
from app.risk.models import RiskState

if TYPE_CHECKING:
    from app.market.gateway import MarketDataGateway


def _store_record_to_managed_position(record: PositionStoreRecord) -> ManagedPosition:
    """Convert PositionStoreRecord to ManagedPosition for evaluation."""
    return ManagedPosition(
        position_id=record.position_id,
        symbol=record.symbol,
        instrument_type=record.instrument_type,  # type: ignore[arg-type]
        side=record.side,  # type: ignore[arg-type]
        entry_execution_id=record.entry_execution_id,
        entry_order_id=record.entry_order_id,
        instrument_plan_id=record.instrument_plan_id,
        entry_timestamp=record.entry_timestamp,
        entry_price=record.entry_price,
        initial_quantity=record.initial_quantity,
        current_quantity=record.current_quantity,
        current_price=record.current_price,
        initial_notional=record.initial_notional,
        current_notional=record.current_notional,
        risk_budget_at_entry=record.risk_budget_at_entry,
        constitution_version=record.constitution_version,
        initial_stop_reference=record.initial_stop_reference,
        current_stop_reference=record.current_stop_reference,
        highest_price_since_entry=record.highest_price_since_entry,
        lowest_price_since_entry=record.lowest_price_since_entry,
        unrealized_pnl=record.unrealized_pnl,
        unrealized_pnl_pct=record.unrealized_pnl_pct,
        realized_pnl=record.realized_pnl,
        status=PositionStatus(record.status),
        exit_state=ExitState(record.exit_state),
        created_at=record.created_at,
        updated_at=record.updated_at,
        mfe=record.mfe,
        mae=record.mae,
    )


class PositionMonitorService:
    """Main position monitoring service - evaluates positions for exits."""

    def __init__(
        self,
        market_gateway: MarketDataGateway,
        alpaca_gateway: AlpacaGateway,
        position_store: PositionStore,
        position_reconciler: PositionReconciler | None = None,
        metrics: PositionMetrics | None = None,
        exit_rules: ExitRulesEngine | None = None,
    ) -> None:
        self._market = market_gateway
        self._alpaca = alpaca_gateway
        self._store = position_store
        self._reconciler = position_reconciler or PositionReconciler(alpaca_gateway, position_store)
        self._metrics = metrics or PositionMetrics()
        self._exit_rules = exit_rules or ExitRulesEngine()

    def monitor_once(
        self,
        risk_state: RiskState,
        dry_run: bool = True,
    ) -> list[ExitDecision]:
        """
        Single monitoring pass for all managed positions.
        Returns list of exit decisions.
        """
        # 1. Load open positions (as store records)
        records = self._store.get_open_positions()
        if not records:
            return []

        # 2. Reconcile with provider
        reconciliation_results = self._reconciler.reconcile_all()
        self._apply_reconciliation(reconciliation_results)

        # 3. Reload positions after reconciliation
        records = self._store.get_open_positions()

        # 4. Evaluate each position
        decisions = []
        for record in records:
            position = _store_record_to_managed_position(record)
            decision = self._evaluate_position(position, risk_state)
            decisions.append(decision)

        return decisions

    def _apply_reconciliation(self, results: list[PositionReconciliationResult]) -> None:
        """Apply reconciliation results to local store."""
        for result in results:
            if not result.reconciled and result.action_required:
                # Mark position as needing reconciliation
                if self._store:
                    self._store.update_status(
                        result.position_id,
                        PositionStatus.RECONCILIATION_REQUIRED,
                    )

    def _evaluate_position(
        self,
        position: ManagedPosition,
        risk_state: RiskState,
    ) -> ExitDecision:
        """Evaluate a single position for exit signals."""
        # Get fresh market state
        market_state = None
        try:
            from app.market import MarketStateBuilder
            builder = MarketStateBuilder(self._market)
            market_state = builder.build(position.symbol)
        except Exception:
            market_state = None

        # Compute position snapshot with metrics
        snapshot = self._metrics.compute_snapshot(position, market_state)

        # Get current risk state
        # Use provided risk_state

        # Evaluate exit rules
        reasons, urgency, decision_type = self._exit_rules.evaluate(
            position, snapshot, risk_state, market_state
        )

        # Determine target quantity
        target_qty = Decimal("0")
        remaining_qty = position.current_quantity
        if decision_type == ExitDecisionType.EXIT:
            target_qty = position.current_quantity
            remaining_qty = Decimal("0")
        elif decision_type == ExitDecisionType.REDUCE:
            # For now, reduce by 50% - could be made configurable
            target_qty = position.current_quantity / Decimal("2")
            remaining_qty = position.current_quantity - target_qty

        # Build exit decision
        reference_price = snapshot.midpoint or position.current_price
        fresh_bid = snapshot.bid_price
        fresh_ask = snapshot.ask_price
        fresh_mid = snapshot.midpoint

        return ExitDecision(
            position_id=position.position_id,
            symbol=position.symbol,
            decision=decision_type,
            reason_codes=tuple(reasons),
            urgency=urgency,
            target_quantity_to_close=target_qty,
            quantity_remaining=remaining_qty,
            reference_price=reference_price,
            fresh_bid=fresh_bid,
            fresh_ask=fresh_ask,
            fresh_mid=fresh_mid,
            evaluated_at=datetime.now(UTC),
        )

    def get_position_snapshot(self, position_id: str) -> PositionSnapshot | None:
        """Get fresh snapshot for a specific position."""
        record = self._store.get_by_position_id(position_id)
        if not record:
            return None

        position = _store_record_to_managed_position(record)

        market_state = None
        try:
            from app.market import MarketStateBuilder
            builder = MarketStateBuilder(self._market)
            market_state = builder.build(position.symbol)
        except Exception:
            market_state = None

        return self._metrics.compute_snapshot(position, market_state)


def create_position_monitor_service(
    market_gateway: MarketDataGateway,
    alpaca_gateway: AlpacaGateway,
    position_store: PositionStore,
    position_reconciler: PositionReconciler | None = None,
    metrics: PositionMetrics | None = None,
    exit_rules: ExitRulesEngine | None = None,
) -> PositionMonitorService:
    """Factory function to create position monitor service."""
    return PositionMonitorService(
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
        position_reconciler=position_reconciler,
        metrics=metrics,
        exit_rules=exit_rules,
    )