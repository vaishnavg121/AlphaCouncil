"""Execution Authorization - Deterministic authorization with structured reason codes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.execution.models import (
    ExecutionAuthorization,
    ExecutionAuthorizationState,
    ExecutionPlan,
    ExecutionReasonCode,
)
from app.execution.validation import ExecutionValidator, create_execution_validator
from app.instruments.models import InstrumentPlan
from app.risk.models import RiskEvaluation, RiskState

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway


class ExecutionAuthorizer:
    """Deterministic execution authorization - AI proposes, M6 authorizes."""

    def __init__(
        self,
        settings: Settings,
        validator: ExecutionValidator,
    ) -> None:
        self._settings = settings
        self._validator = validator

    def authorize(
        self,
        execution_plan: ExecutionPlan,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
        risk_state: RiskState | None = None,
    ) -> ExecutionAuthorization:
        """Authorize or deny execution plan with full reason codes."""
        all_reasons: list[ExecutionReasonCode] = []
        checks: list[str] = []

        # 1. Execution configuration
        config_ok, config_reasons = self._validator.validate_execution_config()
        all_reasons.extend(config_reasons)
        checks.append(f"config={'ok' if config_ok else 'fail'}")

        # 2. Upstream gates (M3/M4/M5)
        upstream_ok, upstream_reasons = self._validator.validate_upstream_gates(instrument_plan)
        all_reasons.extend(upstream_reasons)
        checks.append(f"upstream={'ok' if upstream_ok else 'fail'}")

        # 3. M4 authority revalidation
        m4_ok, m4_reasons = self._validator.validate_m4_authority(risk_evaluation, risk_state)
        all_reasons.extend(m4_reasons)
        checks.append(f"m4_authority={'ok' if m4_ok else 'fail'}")

        # 4. Execution plan validation
        plan_ok, plan_reasons = self._validator.validate_execution_plan(
            execution_plan, instrument_plan, risk_evaluation
        )
        all_reasons.extend(plan_reasons)
        checks.append(f"plan={'ok' if plan_ok else 'fail'}")

        # Determine final state
        is_authorized = len(all_reasons) == 0
        final_reason = ExecutionReasonCode.WITHIN_LIMITS if is_authorized else all_reasons[0]

        return ExecutionAuthorization(
            execution_plan_id=execution_plan.execution_plan_id,
            state=(
                ExecutionAuthorizationState.AUTHORIZED
                if is_authorized
                else ExecutionAuthorizationState.DENIED
            ),
            reason_code=final_reason,
            checks=tuple(checks),
            authorized_at=datetime.now(UTC),
        )


def create_execution_authorizer(
    settings: Settings | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
) -> ExecutionAuthorizer:
    """Factory function to create execution authorizer."""
    if settings is None:
        settings = Settings()
    validator = create_execution_validator(settings, alpaca_gateway)
    return ExecutionAuthorizer(settings, validator)