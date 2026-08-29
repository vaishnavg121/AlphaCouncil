"""Execution Service - Orchestrates complete M6 execution pipeline.

M5 InstrumentPlan -> Planning -> Validation -> Authorization -> Idempotency
-> Gateway -> Tracking -> Result
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.execution.authorization import (
    ExecutionAuthorizer,
    create_execution_authorizer,
)
from app.execution.gateway import PaperExecutionGateway
from app.execution.idempotency import IdempotencyManager
from app.execution.models import (
    ClientOrderId,
    ExecutionAuthorization,
    ExecutionAuthorizationState,
    ExecutionPlan,
    ExecutionReasonCode,
    ExecutionReconciliationResult,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStoreRecord,
    IdempotencyKey,
    OrderSide,
    OrderType,
    PositionIntent,
)
from app.execution.planner import ExecutionPlanner, create_execution_planner
from app.execution.reconciliation import (
    ExecutionReconciler,
    create_execution_reconciler,
)
from app.execution.store import ExecutionStore, create_execution_store
from app.execution.tracking import OrderTracker, create_order_tracker
from app.execution.validation import ExecutionValidator, create_execution_validator

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway
    from app.instruments.models import InstrumentPlan
    from app.market.gateway import MarketDataGateway
    from app.risk.models import RiskEvaluation, RiskState


class ExecutionService:
    """Main M6 execution service - deterministic, safe, auditable."""

    def __init__(
        self,
        settings: Settings,
        market_gateway: MarketDataGateway,
        alpaca_gateway: AlpacaGateway,
        execution_store: ExecutionStore | None = None,
        paper_gateway: PaperExecutionGateway | None = None,
        planner: ExecutionPlanner | None = None,
        validator: ExecutionValidator | None = None,
        authorizer: ExecutionAuthorizer | None = None,
        idempotency_manager: IdempotencyManager | None = None,
        tracker: OrderTracker | None = None,
        reconciler: ExecutionReconciler | None = None,
    ) -> None:
        self._settings = settings
        self._market = market_gateway
        self._alpaca = alpaca_gateway

        # Core components
        self._store = execution_store or create_execution_store()
        self._gateway = paper_gateway or PaperExecutionGateway.from_settings(settings)
        self._planner = planner or create_execution_planner(
            settings, market_gateway, alpaca_gateway
        )
        self._validator = validator or create_execution_validator(
            settings, alpaca_gateway
        )
        self._authorizer = authorizer or create_execution_authorizer(
            settings, alpaca_gateway
        )
        self._idempotency = idempotency_manager or IdempotencyManager(
            self._store, self._gateway
        )
        self._tracker = tracker or create_order_tracker(
            settings, self._gateway, self._store
        )
        self._reconciler = reconciler or create_execution_reconciler(
            self._gateway, self._store
        )

    def execute(
        self,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
        risk_state: RiskState | None = None,
        dry_run: bool = True,
        track: bool = False,
    ) -> ExecutionResult:
        """Execute the complete M6 pipeline.

        Args:
            instrument_plan: M5 instrument selection result
            risk_evaluation: M4 risk evaluation result
            risk_state: Current M4 risk state (for kill switch)
            dry_run: If True, perform all validation but ZERO submit_order calls
            track: If True, poll for order status until terminal or timeout

        Returns:
            ExecutionResult with complete execution lifecycle state
        """
        # 1. Build execution plan with fresh market data
        execution_plan = self._planner.build_execution_plan(
            instrument_plan, risk_evaluation
        )

        # 2. Authorize
        authorization = self._authorizer.authorize(
            execution_plan, instrument_plan, risk_evaluation, risk_state
        )

        if not authorization.is_authorized:
            return self._build_denied_result(
                execution_plan, authorization, instrument_plan.plan_id
            )

        # 3. Idempotency check
        idempotency_key = self._idempotency.generate_idempotency_key(
            instrument_plan, risk_evaluation
        )
        client_order_id = self._idempotency.generate_client_order_id(idempotency_key)

        # Check local store
        existing_local = self._idempotency.check_duplicate_local(idempotency_key)
        if existing_local and existing_local.provider_order_id:
            # Already submitted - adopt existing
            return self._build_adopted_result(
                execution_plan, authorization, existing_local, instrument_plan.plan_id
            )

        # Check provider
        existing_provider = self._idempotency.check_duplicate_provider(client_order_id)
        if existing_provider:
            # Adopt provider order
            adopted_record = self._idempotency.adopt_existing_order(existing_provider)
            return self._build_adopted_result(
                execution_plan, authorization, adopted_record, instrument_plan.plan_id
            )

        # 4. If dry run, return authorized result without submission
        if dry_run:
            return self._build_dry_run_result(
                execution_plan, authorization, instrument_plan.plan_id,
                client_order_id.to_string()
            )

        # 5. Submit order
        return self._submit_and_track(
            execution_plan,
            authorization,
            instrument_plan,
            risk_evaluation,
            idempotency_key,
            client_order_id,
            track,
        )

    def _submit_and_track(
        self,
        execution_plan: ExecutionPlan,
        authorization: ExecutionAuthorization,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
        idempotency_key: IdempotencyKey,
        client_order_id: ClientOrderId,
        track: bool,
    ) -> ExecutionResult:
        """Submit order and optionally track."""
        # Create store record before submission
        record = ExecutionStoreRecord(
            execution_plan_id=execution_plan.execution_plan_id,
            instrument_plan_id=instrument_plan.plan_id,
            idempotency_key=idempotency_key.to_string(),
            client_order_id=client_order_id.to_string(),
            authorization_state=ExecutionAuthorizationState.AUTHORIZED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._store.upsert(record)

        try:
            # Submit based on order type
            if execution_plan.order_type == OrderType.LIMIT:
                order = self._gateway.submit_limit_order(
                    symbol=execution_plan.symbol,
                    side=execution_plan.side,
                    quantity=execution_plan.quantity,
                    limit_price=execution_plan.limit_price,
                    time_in_force=execution_plan.time_in_force,
                    client_order_id=client_order_id.to_string(),
                    position_intent=self._get_position_intent(
                        instrument_plan, execution_plan
                    ),
                )
            else:
                order = self._gateway.submit_market_order(
                    symbol=execution_plan.symbol,
                    side=execution_plan.side,
                    quantity=execution_plan.quantity,
                    time_in_force=execution_plan.time_in_force,
                    client_order_id=client_order_id.to_string(),
                    position_intent=self._get_position_intent(
                        instrument_plan, execution_plan
                    ),
                )

            # Update store with provider info
            self._store.update_provider_info(
                execution_plan.execution_plan_id,
                order.order_id,
                order.provider_status,
                order.submitted_at,
            )

            # Build result
            result = ExecutionResult(
                execution_plan_id=execution_plan.execution_plan_id,
                instrument_plan_id=instrument_plan.plan_id,
                status=order.status,
                authorization=authorization,
                execution_plan=execution_plan,
                execution_order=order,
                created_at=execution_plan.created_at,
                authorized_at=authorization.authorized_at,
                submitted_at=order.submitted_at,
                completed_at=order.filled_at if order.is_filled else None,
            )

            # Track if requested
            if track and order.is_active:
                return self._tracker.track_order(result)

            return result

        except Exception as e:
            # Update store with failure
            self._store.update_status(execution_plan.execution_plan_id, f"FAILED: {e}")
            return ExecutionResult(
                execution_plan_id=execution_plan.execution_plan_id,
                instrument_plan_id=instrument_plan.plan_id,
                status=ExecutionStatus.FAILED,
                authorization=authorization,
                execution_plan=execution_plan,
                reason_codes=(ExecutionReasonCode.PROVIDER_ERROR,),
                warnings=(str(e),),
                created_at=execution_plan.created_at,
                authorized_at=authorization.authorized_at,
            )

    def _get_position_intent(
        self,
        instrument_plan: InstrumentPlan,
        execution_plan: ExecutionPlan,
    ) -> PositionIntent | None:
        """Determine position intent for options."""
        if execution_plan.instrument_type.value == "OPTION":
            # Long options only
            return PositionIntent.BUY_TO_OPEN
        return None

    def _build_denied_result(
        self,
        execution_plan: ExecutionPlan,
        authorization: ExecutionAuthorization,
        instrument_plan_id: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            execution_plan_id=execution_plan.execution_plan_id,
            instrument_plan_id=instrument_plan_id,
            status=ExecutionStatus.NOT_EXECUTED,
            authorization=authorization,
            execution_plan=execution_plan,
            reason_codes=(authorization.reason_code,),
            created_at=execution_plan.created_at,
            authorized_at=authorization.authorized_at,
        )

    def _build_dry_run_result(
        self,
        execution_plan: ExecutionPlan,
        authorization: ExecutionAuthorization,
        instrument_plan_id: str,
        client_order_id: str,
    ) -> ExecutionResult:
        warnings = list(execution_plan.warnings)
        warnings.append(
            "DRY RUN - Would submit "
            f"{execution_plan.order_type.value} {execution_plan.side.value} "
            f"{execution_plan.quantity} {execution_plan.symbol} "
            f"@ {execution_plan.limit_price}"
        )
        warnings.append(f"DRY RUN - Client Order ID: {client_order_id}")

        return ExecutionResult(
            execution_plan_id=execution_plan.execution_plan_id,
            instrument_plan_id=instrument_plan_id,
            status=ExecutionStatus.AUTHORIZED,
            authorization=authorization,
            execution_plan=execution_plan,
            warnings=tuple(warnings),
            reason_codes=(ExecutionReasonCode.WITHIN_LIMITS,),
            created_at=execution_plan.created_at,
            authorized_at=authorization.authorized_at,
        )

    def _build_adopted_result(
        self,
        execution_plan: ExecutionPlan,
        authorization: ExecutionAuthorization,
        existing_record: ExecutionStoreRecord,
        instrument_plan_id: str,
    ) -> ExecutionResult:
        """Build result for adopted existing order."""
        # Fetch current order status from provider
        order = None
        if existing_record.provider_order_id:
            try:
                order = self._gateway.get_order_by_id(
                    existing_record.provider_order_id
                )
            except Exception:
                pass

        warnings = list(execution_plan.warnings)
        warnings.append(
            f"DUPLICATE DETECTED - Adopted existing order "
            f"{existing_record.provider_order_id}"
        )

        return ExecutionResult(
            execution_plan_id=execution_plan.execution_plan_id,
            instrument_plan_id=instrument_plan_id,
            status=order.status if order else ExecutionStatus.UNKNOWN,
            authorization=authorization,
            execution_plan=execution_plan,
            execution_order=order,
            warnings=tuple(warnings),
            reason_codes=(ExecutionReasonCode.DUPLICATE_EXECUTION,),
            created_at=execution_plan.created_at,
            authorized_at=authorization.authorized_at,
            submitted_at=order.submitted_at
            if order
            else existing_record.submitted_at,
        )

    def reconcile_all(self) -> list[ExecutionReconciliationResult]:
        """Run crash recovery reconciliation for all pending executions."""
        return self._reconciler.reconcile_pending_executions()

    def get_execution_status(
        self, execution_plan_id: str
    ) -> ExecutionResult | None:
        """Get current execution status by plan ID."""
        record = self._store.get_by_execution_plan_id(execution_plan_id)
        if not record:
            return None

        order = None
        if record.provider_order_id:
            try:
                order = self._gateway.get_order_by_id(record.provider_order_id)
            except Exception:
                pass

        # Create a minimal execution plan for the result
        from app.execution.models import (
            ExecutionPlan,
            InstrumentType,
            OrderType,
            TimeInForce,
        )

        minimal_plan = ExecutionPlan(
            execution_plan_id=record.execution_plan_id,
            instrument_plan_id=record.instrument_plan_id,
            created_at=record.created_at,
            expires_at=record.created_at,
            symbol="",
            instrument_type=InstrumentType.STOCK,
            direction="BULLISH",
            side=OrderSide.BUY,
            quantity=Decimal("0"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=Decimal("0"),
            fresh_bid=Decimal("0"),
            fresh_ask=Decimal("0"),
            fresh_mid=Decimal("0"),
            fresh_quote_timestamp=record.created_at,
            limit_price=Decimal("0"),
            expected_notional=Decimal("0"),
            risk_budget=Decimal("0"),
            max_authorized_notional=Decimal("0"),
            constitution_version="v1",
        )

        return ExecutionResult(
            execution_plan_id=record.execution_plan_id,
            instrument_plan_id=record.instrument_plan_id,
            status=order.status if order else ExecutionStatus.UNKNOWN,
            authorization=ExecutionAuthorization(
                execution_plan_id=record.execution_plan_id,
                state=record.authorization_state,
                reason_code=ExecutionReasonCode.WITHIN_LIMITS,
            ),
            execution_plan=minimal_plan,
            execution_order=order,
            created_at=record.created_at,
            submitted_at=record.submitted_at,
        )


def create_execution_service(
    settings: Settings | None = None,
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
    execution_store: ExecutionStore | None = None,
) -> ExecutionService:
    """Factory function to create execution service."""
    if settings is None:
        settings = Settings()
    if market_gateway is None:
        from app.market import AlpacaMarketDataGateway

        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    if alpaca_gateway is None:
        from app.alpaca.gateway import AlpacaGateway

        alpaca_gateway = AlpacaGateway.from_settings(settings)

    return ExecutionService(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        execution_store=execution_store,
    )