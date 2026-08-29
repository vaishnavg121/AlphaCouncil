"""Idempotency and Duplicate Protection for M6 Execution."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from app.execution.gateway import PaperExecutionGateway
from app.execution.models import (
    ClientOrderId,
    ExecutionAuthorizationState,
    ExecutionOrder,
    ExecutionStoreRecord,
    IdempotencyKey,
    OrderSide,
)
from app.execution.store import ExecutionStore

if TYPE_CHECKING:
    from app.instruments.models import InstrumentPlan
    from app.risk.models import RiskEvaluation


class IdempotencyManager:
    """Manages idempotency keys and duplicate protection."""

    def __init__(self, store: ExecutionStore, gateway: PaperExecutionGateway) -> None:
        self._store = store
        self._gateway = gateway

    def generate_idempotency_key(
        self,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
    ) -> IdempotencyKey:
        """Generate deterministic idempotency key from stable execution identity."""
        if instrument_plan.equity_plan:
            side = (
                OrderSide.BUY
                if instrument_plan.equity_plan.side.value == "LONG"
                else OrderSide.SELL
            )
            quantity = instrument_plan.equity_plan.estimated_quantity
        elif instrument_plan.option_plan:
            side = OrderSide.BUY  # Long options only
            quantity = Decimal(str(instrument_plan.option_plan.planned_contracts))
        else:
            raise ValueError("Invalid instrument plan: no equity or option plan")

        return IdempotencyKey(
            instrument_plan_id=instrument_plan.plan_id,
            symbol=instrument_plan.symbol,
            side=side,
            quantity=quantity,
            risk_authorization_version=risk_evaluation.constitution_version,
        )

    def generate_client_order_id(self, idempotency_key: IdempotencyKey) -> ClientOrderId:
        """Generate Alpaca client_order_id from idempotency key."""
        return ClientOrderId(idempotency_key=idempotency_key.to_string())

    def check_duplicate_local(self, idempotency_key: IdempotencyKey) -> ExecutionStoreRecord | None:
        """Check local store for existing execution with same idempotency key."""
        return self._store.get_by_idempotency_key(idempotency_key.to_string())

    def check_duplicate_provider(self, client_order_id: ClientOrderId) -> ExecutionOrder | None:
        """Check Alpaca for existing order with same client_order_id."""
        order = self._gateway.get_order_by_client_id(client_order_id.to_string())
        if order:
            return order
        return None

    def adopt_existing_order(self, existing_order: ExecutionOrder) -> ExecutionStoreRecord:
        """Adopt an existing order found during duplicate check."""
        # Update local store with provider order info
        record = ExecutionStoreRecord(
            execution_plan_id=existing_order.client_order_id.replace("ac-", ""),
            instrument_plan_id=existing_order.client_order_id.replace("ac-", ""),
            idempotency_key=existing_order.client_order_id,
            client_order_id=existing_order.client_order_id,
            authorization_state=ExecutionAuthorizationState.AUTHORIZED,
            provider_order_id=existing_order.order_id,
            provider_status=existing_order.provider_status,
            created_at=existing_order.submitted_at,
            submitted_at=existing_order.submitted_at,
            updated_at=existing_order.submitted_at,
        )
        self._store.upsert(record)
        return record