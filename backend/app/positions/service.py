"""Exit management service - orchestrates exit execution through M6 gateway."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.execution.authorization import ExecutionAuthorizer, create_execution_authorizer
from app.execution.gateway import PaperExecutionGateway
from app.execution.idempotency import IdempotencyManager
from app.execution.models import (
    ClientOrderId,
    ExecutionAuthorization,
    ExecutionAuthorizationState,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStatus,
    ExecutionStoreRecord,
    IdempotencyKey,
    InstrumentType,
    OrderSide,
    OrderType,
    PositionIntent,
    TimeInForce,
)
from app.execution.planner import ExecutionPlanner, create_execution_planner
from app.execution.reconciliation import ExecutionReconciler, create_execution_reconciler
from app.execution.store import ExecutionStore, create_execution_store
from app.execution.tracking import OrderTracker, create_order_tracker
from app.execution.validation import ExecutionValidator, create_execution_validator
from app.positions.metrics import ExitRulesEngine
from app.positions.models import (
    ExitExecutionResult,
    ExitPlan,
    ManagedPosition,
)
from app.positions.reconciliation import PositionReconciler
from app.positions.store import PositionStore, create_position_store
from app.risk.models import RiskState

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway
    from app.market.gateway import MarketDataGateway


class ExitManagementService:
    """Main M7 exit management service - reuses M6 execution infrastructure."""

    def __init__(
        self,
        settings: Settings,
        market_gateway: MarketDataGateway,
        alpaca_gateway: AlpacaGateway,
        position_store: PositionStore,
        execution_store: ExecutionStore | None = None,
        paper_gateway: PaperExecutionGateway | None = None,
        execution_planner: ExecutionPlanner | None = None,
        execution_validator: ExecutionValidator | None = None,
        execution_authorizer: ExecutionAuthorizer | None = None,
        idempotency_manager: IdempotencyManager | None = None,
        order_tracker: OrderTracker | None = None,
        execution_reconciler: ExecutionReconciler | None = None,
        position_reconciler: PositionReconciler | None = None,
    ) -> None:
        self._settings = settings
        self._market = market_gateway
        self._alpaca = alpaca_gateway
        self._position_store = position_store

        # M6 execution components (reused)
        self._exec_store = execution_store or create_execution_store()
        self._gateway = paper_gateway or PaperExecutionGateway.from_settings(settings)
        self._planner = execution_planner or create_execution_planner(settings, market_gateway, alpaca_gateway)
        self._validator = execution_validator or create_execution_validator(settings, alpaca_gateway)
        self._authorizer = execution_authorizer or create_execution_authorizer(settings, alpaca_gateway)
        self._idempotency = idempotency_manager or IdempotencyManager(self._exec_store, self._gateway)
        self._tracker = order_tracker or create_order_tracker(settings, self._gateway, self._exec_store)
        self._exec_reconciler = execution_reconciler or create_execution_reconciler(self._gateway, self._exec_store)

        # M7 position components
        self._position_reconciler = position_reconciler or PositionReconciler(alpaca_gateway, position_store)
        self._exit_rules = ExitRulesEngine()

    def execute_exit(
        self,
        exit_plan: ExitPlan,
        position: ManagedPosition,
        risk_state: RiskState | None = None,
        dry_run: bool = True,
        track: bool = False,
    ) -> ExitExecutionResult:
        """Execute an exit plan through M6 gateway infrastructure."""
        # 1. Convert ExitPlan to M6 ExecutionPlan
        execution_plan = self._build_execution_plan(exit_plan, position, risk_state)

        # 2. Authorize using M6 authorizer
        # Create a minimal risk evaluation for authorization
        from app.instruments.models import (
            EquityInstrumentPlan,
            EquitySide,
            InstrumentPlan,
            InstrumentType,
        )
        from app.risk.models import RiskBudget, RiskDecisionType, RiskEvaluation, RiskReasonCode
        risk_eval = RiskEvaluation(
            symbol=position.symbol,
            decision=RiskDecisionType.APPROVED,
            reason_code=RiskReasonCode.WITHIN_LIMITS,
            risk_budget=RiskBudget(
                base_risk_budget=Decimal("0"),
                adjusted_risk_budget=Decimal("0"),
                max_position_notional=position.current_notional,
            ),
            constitution_version=position.constitution_version,
        )

        # Create minimal instrument plan for exit authorization
        exit_instrument_plan = InstrumentPlan(
            plan_id=f"exit-{exit_plan.exit_plan_id}",
            created_at=datetime.now(UTC),
            symbol=position.symbol,
            thesis_direction="BEARISH" if position.side == "LONG" else "BULLISH",
            instrument_type=InstrumentType.STOCK if position.instrument_type in ("STOCK", "ETF") else InstrumentType.OPTION,
            underlying_symbol=position.symbol if position.instrument_type == "OPTION" else None,
            equity_plan=EquityInstrumentPlan(
                symbol=position.symbol,
                side=EquitySide.LONG if position.side == "LONG" else EquitySide.SHORT,
                reference_price=exit_plan.reference_price,
                max_notional=position.current_notional,
                planned_notional=exit_plan.expected_notional,
                estimated_quantity=exit_plan.quantity,
                risk_budget_used=Decimal("0"),
                estimated_loss_at_risk_stop=Decimal("0"),
                selection_score=Decimal("0"),
            ),
            selection_reasons=tuple(str(r) for r in exit_plan.reason_codes),
        )

        authorization = self._authorizer.authorize(
            execution_plan,
            exit_instrument_plan,
            risk_eval,
            risk_state,
        )

        if not authorization.is_authorized:
            return ExitExecutionResult(
                exit_plan_id=exit_plan.exit_plan_id,
                position_id=position.position_id,
                execution_status=ExecutionStatus.NOT_EXECUTED.value,
                reason_codes=(str(authorization.reason_code),),
            )

        # 3. Idempotency check
        idempotency_key = self._generate_exit_idempotency_key(exit_plan, position)
        client_order_id = self._idempotency.generate_client_order_id(idempotency_key)

        # Check local store
        existing_local = self._idempotency.check_duplicate_local(idempotency_key)
        if existing_local and existing_local.provider_order_id:
            return self._build_adopted_exit_result(exit_plan, position, existing_local)

        # Check provider
        existing_provider = self._idempotency.check_duplicate_provider(client_order_id)
        if existing_provider:
            adopted = self._idempotency.adopt_existing_order(existing_provider)
            return self._build_adopted_exit_result(exit_plan, position, adopted)

        # 4. Dry run
        if dry_run:
            return ExitExecutionResult(
                exit_plan_id=exit_plan.exit_plan_id,
                position_id=position.position_id,
                execution_status=ExecutionStatus.AUTHORIZED.value,
                execution_order_id=client_order_id.to_string(),
                warnings=(
                    f"DRY RUN - Would submit {exit_plan.side} {exit_plan.quantity} "
                    f"{exit_plan.symbol} @ {exit_plan.limit_price}",
                    f"DRY RUN - Client Order ID: {client_order_id.to_string()}",
                ),
            )

        # 5. Submit order through M6 gateway
        return self._submit_exit_order(
            execution_plan,
            authorization,
            exit_plan,
            position,
            idempotency_key,
            client_order_id,
            track,
        )

    def _build_execution_plan(
        self,
        exit_plan: ExitPlan,
        position: ManagedPosition,
        risk_state: RiskState | None,
    ) -> ExecutionPlan:
        """Convert ExitPlan to M6 ExecutionPlan."""
        now = datetime.now(UTC)
        ttl_seconds = self._settings.execution_plan_ttl_seconds
        expires_at = now + timedelta(seconds=ttl_seconds)

        # Map exit side to M6 OrderSide
        side_map = {
            "SELL": OrderSide.SELL,
            "BUY_TO_COVER": OrderSide.BUY,
            "SELL_TO_CLOSE": OrderSide.SELL,
        }

        return ExecutionPlan(
            execution_plan_id=f"exit-{exit_plan.exit_plan_id}",
            instrument_plan_id=position.instrument_plan_id,
            created_at=now,
            expires_at=expires_at,
            symbol=exit_plan.symbol,
            instrument_type=(
                InstrumentType.STOCK if position.instrument_type in ("STOCK", "ETF") else InstrumentType.OPTION
            ),
            direction="BEARISH" if position.side == "LONG" else "BULLISH",
            side=side_map.get(exit_plan.side, OrderSide.SELL),
            quantity=exit_plan.quantity,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            m5_reference_price=exit_plan.reference_price,
            fresh_bid=exit_plan.fresh_bid or Decimal("0"),
            fresh_ask=exit_plan.fresh_ask or Decimal("0"),
            fresh_mid=exit_plan.fresh_mid or exit_plan.reference_price,
            fresh_quote_timestamp=datetime.now(UTC),
            limit_price=exit_plan.limit_price or exit_plan.reference_price,
            expected_notional=exit_plan.expected_notional,
            risk_budget=Decimal("0"),
            max_authorized_notional=position.current_notional,
            constitution_version=exit_plan.constitution_version,
        )

    def _generate_exit_idempotency_key(
        self,
        exit_plan: ExitPlan,
        position: ManagedPosition,
    ) -> IdempotencyKey:
        """Generate deterministic idempotency key for exit."""
        return IdempotencyKey(
            instrument_plan_id=f"exit-{position.position_id}",
            symbol=position.symbol,
            side=OrderSide.SELL if position.side == "LONG" else OrderSide.BUY,
            quantity=exit_plan.quantity,
            risk_authorization_version=position.constitution_version,
        )

    def _submit_exit_order(
        self,
        execution_plan: ExecutionPlan,
        authorization: ExecutionAuthorization,
        exit_plan: ExitPlan,
        position: ManagedPosition,
        idempotency_key: IdempotencyKey,
        client_order_id: ClientOrderId,
        track: bool,
    ) -> ExitExecutionResult:
        """Submit exit order through M6 gateway."""
        # Create store record
        record = ExecutionStoreRecord(
            execution_plan_id=execution_plan.execution_plan_id,
            instrument_plan_id=position.instrument_plan_id,
            idempotency_key=idempotency_key.to_string(),
            client_order_id=client_order_id.to_string(),
            authorization_state=ExecutionAuthorizationState.AUTHORIZED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._exec_store.upsert(record)

        try:
            # Determine position intent for exit
            if position.instrument_type == "OPTION":
                position_intent = PositionIntent.SELL_TO_CLOSE
            elif position.side == "LONG":
                position_intent = PositionIntent.SELL_TO_CLOSE
            else:
                position_intent = PositionIntent.BUY_TO_CLOSE

            # Submit order
            order = self._gateway.submit_limit_order(
                symbol=execution_plan.symbol,
                side=execution_plan.side,
                quantity=execution_plan.quantity,
                limit_price=execution_plan.limit_price,
                time_in_force=execution_plan.time_in_force,
                client_order_id=client_order_id.to_string(),
                position_intent=position_intent,
            )

            # Update store
            self._exec_store.update_provider_info(
                execution_plan.execution_plan_id,
                order.order_id,
                order.provider_status,
                order.submitted_at,
            )

            # Build result
            result = ExitExecutionResult(
                exit_plan_id=exit_plan.exit_plan_id,
                position_id=position.position_id,
                execution_result_id=order.order_id,
                execution_status=order.status.value,
                execution_order_id=order.order_id,
                filled_quantity=order.filled_quantity,
                filled_avg_price=order.filled_avg_price,
                remaining_quantity=exit_plan.quantity - order.filled_quantity,
                submitted_at=order.submitted_at,
                completed_at=order.filled_at if order.is_filled else None,
            )

            # Track if requested
            if track and order.is_active:
                track_now = datetime.now(UTC)
                exec_result = ExecutionResult(
                    execution_plan_id=execution_plan.execution_plan_id,
                    instrument_plan_id=position.instrument_plan_id,
                    status=order.status,
                    authorization=authorization,
                    execution_plan=ExecutionPlan(
                        execution_plan_id=execution_plan.execution_plan_id,
                        instrument_plan_id=position.instrument_plan_id,
                        created_at=track_now,
                        expires_at=track_now,
                        symbol="",
                        instrument_type=InstrumentType.STOCK,
                        direction="BEARISH",
                        side=OrderSide.SELL,
                        quantity=Decimal("0"),
                        order_type=OrderType.LIMIT,
                        time_in_force=TimeInForce.DAY,
                        m5_reference_price=Decimal("0"),
                        fresh_bid=Decimal("0"),
                        fresh_ask=Decimal("0"),
                        fresh_mid=Decimal("0"),
                        fresh_quote_timestamp=track_now,
                        limit_price=Decimal("0"),
                        expected_notional=Decimal("0"),
                        risk_budget=Decimal("0"),
                        max_authorized_notional=Decimal("0"),
                        constitution_version="v1",
                    ),
                    execution_order=order,
                    created_at=track_now,
                    authorized_at=authorization.authorized_at,
                    submitted_at=order.submitted_at,
                )
                tracked = self._tracker.track_order(exec_result)
                result.execution_status = tracked.status.value
                result.filled_quantity = tracked.execution_order.filled_quantity if tracked.execution_order else Decimal("0")
                result.filled_avg_price = tracked.execution_order.filled_avg_price if tracked.execution_order else None
                result.completed_at = tracked.completed_at

            return result

        except Exception as e:
            self._exec_store.update_status(execution_plan.execution_plan_id, f"FAILED: {e}")
            return ExitExecutionResult(
                exit_plan_id=exit_plan.exit_plan_id,
                position_id=position.position_id,
                execution_status=ExecutionStatus.FAILED.value,
                reason_codes=(str(e),),
                warnings=(str(e),),
            )

    def _build_adopted_exit_result(
        self,
        exit_plan: ExitPlan,
        position: ManagedPosition,
        existing_record: ExecutionStoreRecord,
    ) -> ExitExecutionResult:
        """Build result for adopted existing exit order."""
        order = None
        if existing_record.provider_order_id:
            try:
                order = self._gateway.get_order_by_id(existing_record.provider_order_id)
            except Exception:
                pass

        return ExitExecutionResult(
            exit_plan_id=exit_plan.exit_plan_id,
            position_id=position.position_id,
            execution_result_id=order.order_id if order else existing_record.provider_order_id,
            execution_status=order.status.value if order else "UNKNOWN",
            execution_order_id=order.order_id if order else existing_record.provider_order_id,
            filled_quantity=order.filled_quantity if order else Decimal("0"),
            filled_avg_price=order.filled_avg_price if order else None,
            remaining_quantity=exit_plan.quantity - (order.filled_quantity if order else Decimal("0")),
            warnings=(f"DUPLICATE DETECTED - Adopted existing exit order {existing_record.provider_order_id}",),
            submitted_at=order.submitted_at if order else existing_record.submitted_at,
        )

    def reconcile_exit(self, exit_plan_id: str) -> ExitExecutionResult | None:
        """Reconcile an exit execution after restart."""
        # Find execution record
        records = self._exec_store.get_pending_executions()
        for record in records:
            if record.execution_plan_id.startswith("exit-"):
                order = None
                if record.provider_order_id:
                    try:
                        order = self._gateway.get_order_by_id(record.provider_order_id)
                    except Exception:
                        pass

                if order:
                    self._exec_store.update_provider_info(
                        record.execution_plan_id,
                        order.order_id,
                        order.provider_status,
                        order.submitted_at,
                    )
                    return ExitExecutionResult(
                        exit_plan_id=record.execution_plan_id.replace("exit-", ""),
                        position_id=record.instrument_plan_id,  # Not perfect but workable
                        execution_result_id=order.order_id,
                        execution_status=order.status.value,
                        execution_order_id=order.order_id,
                        filled_quantity=order.filled_quantity,
                        filled_avg_price=order.filled_avg_price,
                        submitted_at=order.submitted_at,
                        completed_at=order.filled_at if order.is_filled else None,
                    )

        return None


def create_exit_management_service(
    settings: Settings | None = None,
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
    position_store: PositionStore | None = None,
    execution_store: ExecutionStore | None = None,
) -> ExitManagementService:
    """Factory function to create exit management service."""
    if settings is None:
        settings = Settings()
    if market_gateway is None:
        from app.market import AlpacaMarketDataGateway
        market_gateway = AlpacaMarketDataGateway.from_settings(settings)
    if alpaca_gateway is None:
        from app.alpaca.gateway import AlpacaGateway
        alpaca_gateway = AlpacaGateway.from_settings(settings)
    if position_store is None:
        position_store = create_position_store()

    return ExitManagementService(
        settings=settings,
        market_gateway=market_gateway,
        alpaca_gateway=alpaca_gateway,
        position_store=position_store,
        execution_store=execution_store,
    )