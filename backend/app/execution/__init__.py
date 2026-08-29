"""M6 Execution package - Safe paper-only execution."""

from app.execution.authorization import ExecutionAuthorizer, create_execution_authorizer
from app.execution.gateway import PaperExecutionGateway
from app.execution.idempotency import IdempotencyManager
from app.execution.models import (
    ClientOrderId,
    ExecutionAuthorization,
    ExecutionAuthorizationState,
    ExecutionOrder,
    ExecutionPlan,
    ExecutionReasonCode,
    ExecutionReconciliationResult,
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
from app.execution.service import ExecutionService, create_execution_service
from app.execution.store import ExecutionStore, create_execution_store
from app.execution.tracking import OrderTracker, create_order_tracker
from app.execution.validation import ExecutionValidator, create_execution_validator

__all__ = [
    # Models
    "ClientOrderId",
    "ExecutionAuthorization",
    "ExecutionAuthorizationState",
    "ExecutionOrder",
    "ExecutionPlan",
    "ExecutionReasonCode",
    "ExecutionReconciliationResult",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutionStoreRecord",
    "IdempotencyKey",
    "InstrumentType",
    "OrderSide",
    "OrderType",
    "PositionIntent",
    "TimeInForce",
    # Gateway
    "PaperExecutionGateway",
    # Planner
    "ExecutionPlanner",
    "create_execution_planner",
    # Validation
    "ExecutionValidator",
    "create_execution_validator",
    # Authorization
    "ExecutionAuthorizer",
    "create_execution_authorizer",
    # Idempotency
    "IdempotencyManager",
    # Store
    "ExecutionStore",
    "create_execution_store",
    # Tracking
    "OrderTracker",
    "create_order_tracker",
    # Reconciliation
    "ExecutionReconciler",
    "create_execution_reconciler",
    # Service
    "ExecutionService",
    "create_execution_service",
]