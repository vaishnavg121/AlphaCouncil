"""Order Status Tracking - Bounded polling for execution status."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.execution.gateway import PaperExecutionGateway
from app.execution.models import ExecutionOrder, ExecutionResult, ExecutionStatus
from app.execution.store import ExecutionStore, create_execution_store

if TYPE_CHECKING:
    pass


class OrderTracker:
    """Bounded order status tracking with timeout."""

    def __init__(
        self,
        settings: Settings,
        gateway: PaperExecutionGateway,
        store: ExecutionStore,
    ) -> None:
        self._settings = settings
        self._gateway = gateway
        self._store = store

    def track_order(
        self,
        execution_result: ExecutionResult,
    ) -> ExecutionResult:
        """Track order status until terminal state or timeout."""
        if not execution_result.execution_order:
            return execution_result

        order_id = execution_result.execution_order.order_id
        client_order_id = execution_result.execution_order.client_order_id
        timeout_seconds = self._settings.execution_track_timeout_seconds
        poll_interval = self._settings.execution_poll_interval_seconds

        start_time = time.monotonic()
        last_status = execution_result.execution_order.status

        while time.monotonic() - start_time < timeout_seconds:
            try:
                # Try by provider order ID first
                if order_id:
                    order = self._gateway.get_order_by_id(order_id)
                else:
                    # Fallback to client_order_id
                    order_opt = self._gateway.get_order_by_client_id(client_order_id)
                    if not order_opt:
                        break
                    order = order_opt

                # Update status
                if order.status != last_status:
                    last_status = order.status
                    # Update store
                    self._store.update_status(
                        execution_result.execution_plan_id,
                        order.provider_status,
                    )

                # Check for terminal state
                if order.is_terminal:
                    return self._build_terminal_result(execution_result, order)

                # Check for fill
                if order.status == ExecutionStatus.FILLED:
                    return self._build_terminal_result(execution_result, order)

                # Wait before next poll
                time.sleep(poll_interval)

            except Exception:
                # On error, continue polling
                time.sleep(poll_interval)
                continue

        # Timeout - return current state as SUBMITTED/OPEN
        return self._build_timeout_result(execution_result, last_status)

    def _build_terminal_result(
        self,
        execution_result: ExecutionResult,
        order: ExecutionOrder,
    ) -> ExecutionResult:
        """Build final ExecutionResult from terminal order."""
        return ExecutionResult(
            execution_plan_id=execution_result.execution_plan_id,
            instrument_plan_id=execution_result.instrument_plan_id,
            status=order.status,
            authorization=execution_result.authorization,
            execution_plan=execution_result.execution_plan,
            execution_order=order,
            warnings=execution_result.warnings,
            reason_codes=execution_result.reason_codes,
            created_at=execution_result.created_at,
            authorized_at=execution_result.authorized_at,
            submitted_at=execution_result.submitted_at,
            completed_at=datetime.now(UTC),
        )

    def _build_timeout_result(
        self,
        execution_result: ExecutionResult,
        last_status: ExecutionStatus,
    ) -> ExecutionResult:
        """Build result after tracking timeout."""
        warnings = list(execution_result.warnings)
        warnings.append(f"Tracking timeout after {self._settings.execution_track_timeout_seconds}s")

        return ExecutionResult(
            execution_plan_id=execution_result.execution_plan_id,
            instrument_plan_id=execution_result.instrument_plan_id,
            status=last_status,  # Keep last known status (SUBMITTED/PARTIALLY_FILLED)
            authorization=execution_result.authorization,
            execution_plan=execution_result.execution_plan,
            execution_order=execution_result.execution_order,
            warnings=tuple(warnings),
            reason_codes=execution_result.reason_codes,
            created_at=execution_result.created_at,
            authorized_at=execution_result.authorized_at,
            submitted_at=execution_result.submitted_at,
            completed_at=None,
        )

    async def track_order_async(
        self,
        execution_result: ExecutionResult,
    ) -> ExecutionResult:
        """Async version of track_order."""
        if not execution_result.execution_order:
            return execution_result

        order_id = execution_result.execution_order.order_id
        client_order_id = execution_result.execution_order.client_order_id
        timeout_seconds = self._settings.execution_track_timeout_seconds
        poll_interval = self._settings.execution_poll_interval_seconds

        start_time = time.monotonic()
        last_status = execution_result.execution_order.status

        while time.monotonic() - start_time < timeout_seconds:
            try:
                if order_id:
                    order = self._gateway.get_order_by_id(order_id)
                else:
                    order_opt = self._gateway.get_order_by_client_id(client_order_id)
                    if not order_opt:
                        break
                    order = order_opt

                if order.status != last_status:
                    last_status = order.status
                    self._store.update_status(
                        execution_result.execution_plan_id,
                        order.provider_status,
                    )

                if order.is_terminal:
                    return self._build_terminal_result(execution_result, order)

                if order.status == ExecutionStatus.FILLED:
                    return self._build_terminal_result(execution_result, order)

                await asyncio.sleep(poll_interval)

            except Exception:
                await asyncio.sleep(poll_interval)
                continue

        return self._build_timeout_result(execution_result, last_status)


def create_order_tracker(
    settings: Settings | None = None,
    gateway: PaperExecutionGateway | None = None,
    store: ExecutionStore | None = None,
) -> OrderTracker:
    """Factory function to create order tracker."""
    if settings is None:
        settings = Settings()
    if gateway is None:
        gateway = PaperExecutionGateway.from_settings(settings)
    if store is None:
        store = create_execution_store()
    return OrderTracker(settings, gateway, store)