"""Crash Recovery and Reconciliation for M6 Execution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.execution.gateway import PaperExecutionGateway
from app.execution.models import (
    ExecutionReconciliationResult,
    ExecutionStoreRecord,
)
from app.execution.store import ExecutionStore, create_execution_store

if TYPE_CHECKING:
    pass


class ExecutionReconciler:
    """Reconciles local execution state with provider after crash/restart."""

    def __init__(
        self,
        gateway: PaperExecutionGateway,
        store: ExecutionStore,
    ) -> None:
        self._gateway = gateway
        self._store = store

    def reconcile_pending_executions(self) -> list[ExecutionReconciliationResult]:
        """Reconcile all pending executions after restart.

        For executions in SUBMITTING/SUBMISSION_UNKNOWN/SUBMITTED state:
        - Query provider using order ID or client_order_id
        - Update local state
        - NEVER create a second order
        """
        pending = self._store.get_pending_executions()
        active = self._store.get_active_executions()
        all_to_reconcile = pending + active

        results = []
        for record in all_to_reconcile:
            result = self._reconcile_record(record)
            results.append(result)

        return results

    def _reconcile_record(self, record: ExecutionStoreRecord) -> ExecutionReconciliationResult:
        """Reconcile a single execution record."""
        provider_order = None

        # Try to find order by provider order ID first
        if record.provider_order_id:
            try:
                provider_order = self._gateway.get_order_by_id(record.provider_order_id)
            except Exception:
                pass

        # If not found, try by client_order_id
        if not provider_order and record.client_order_id:
            try:
                provider_order = self._gateway.get_order_by_client_id(record.client_order_id)
            except Exception:
                pass

        reconciled = provider_order is not None
        action_taken = ""

        if reconciled and provider_order:
            # Update local store with current provider state
            self._store.update_provider_info(
                record.execution_plan_id,
                provider_order.order_id,
                provider_order.provider_status,
                provider_order.submitted_at,
            )
            action_taken = f"Updated local state to {provider_order.provider_status}"
        else:
            # Order not found at provider - could be expired/canceled
            # Mark local record accordingly
            self._store.update_status(record.execution_plan_id, "UNKNOWN_PROVIDER")
            action_taken = "Provider order not found - marked UNKNOWN_PROVIDER"

        return ExecutionReconciliationResult(
            local_record=record,
            provider_order=provider_order,
            reconciled=reconciled,
            action_taken=action_taken,
        )

    def reconcile_specific(self, execution_plan_id: str) -> ExecutionReconciliationResult | None:
        """Reconcile a specific execution by plan ID."""
        record = self._store.get_by_execution_plan_id(execution_plan_id)
        if not record:
            return None
        return self._reconcile_record(record)


def create_execution_reconciler(
    gateway: PaperExecutionGateway | None = None,
    store: ExecutionStore | None = None,
) -> ExecutionReconciler:
    """Factory function to create execution reconciler."""
    if gateway is None:
        from app.core.config import Settings
        gateway = PaperExecutionGateway.from_settings(Settings())
    if store is None:
        store = create_execution_store()
    return ExecutionReconciler(gateway, store)