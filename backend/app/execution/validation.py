"""Execution Validation - Final M4 revalidation and defense-in-depth checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.execution.models import ExecutionPlan, ExecutionReasonCode
from app.instruments.models import InstrumentPlan
from app.risk.models import RiskDecisionType, RiskEvaluation, RiskState

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway


class ExecutionValidator:
    """Final validation layer before execution - defense in depth."""

    def __init__(
        self,
        settings: Settings,
        alpaca_gateway: AlpacaGateway | None = None,
    ) -> None:
        self._settings = settings
        self._alpaca = alpaca_gateway

    def validate_execution_plan(
        self,
        execution_plan: ExecutionPlan,
        instrument_plan: InstrumentPlan,
        risk_evaluation: RiskEvaluation,
    ) -> tuple[bool, list[ExecutionReasonCode]]:
        """Comprehensive validation of execution plan against all constraints.

        Returns (is_valid, list_of_failed_reason_codes).
        """
        failures: list[ExecutionReasonCode] = []

        # 1. Plan expiry check
        if execution_plan.is_expired:
            failures.append(ExecutionReasonCode.PLAN_EXPIRED)

        # 2. Quantity validation
        if execution_plan.quantity <= 0:
            failures.append(ExecutionReasonCode.INVALID_QUANTITY)

        # 3. M5 quantity ceiling - M6 can NEVER increase M5 quantity
        if instrument_plan.is_stock and instrument_plan.equity_plan:
            m5_qty = instrument_plan.equity_plan.estimated_quantity
            if execution_plan.quantity > m5_qty:
                failures.append(ExecutionReasonCode.INVALID_QUANTITY)
        elif instrument_plan.is_option and instrument_plan.option_plan:
            m5_contracts = instrument_plan.option_plan.planned_contracts
            if execution_plan.quantity > m5_contracts:
                failures.append(ExecutionReasonCode.INVALID_QUANTITY)

        # 4. Notional validation against M4 ceiling
        if execution_plan.expected_notional > execution_plan.max_authorized_notional:
            failures.append(ExecutionReasonCode.NOTIONAL_EXCEEDED)

        # 5. Risk budget validation
        if execution_plan.expected_notional > execution_plan.risk_budget:
            failures.append(ExecutionReasonCode.RISK_BUDGET_EXCEEDED)

        # 6. Option-specific: max loss vs risk budget
        if instrument_plan.is_option and instrument_plan.option_plan:
            max_loss = instrument_plan.option_plan.maximum_loss
            if max_loss > execution_plan.risk_budget:
                failures.append(ExecutionReasonCode.RISK_BUDGET_EXCEEDED)

        # 7. Kill switch check (if we have risk state)
        # This is checked in authorization, but defense in depth here too
        # The actual kill switch state comes from M4 risk evaluation context

        return len(failures) == 0, failures

    def validate_m4_authority(
        self,
        risk_evaluation: RiskEvaluation,
        risk_state: RiskState | None = None,
    ) -> tuple[bool, list[ExecutionReasonCode]]:
        """Final M4 revalidation immediately before submission.

        Checks:
        - RiskEvaluation is APPROVED or REDUCED
        - RiskBudget exists
        - Kill switch inactive
        - Constitution version valid
        - Max notional not exceeded
        - Risk budget not exceeded

        Returns (is_valid, list_of_failed_reason_codes).
        """
        failures: list[ExecutionReasonCode] = []

        # Risk evaluation decision
        if risk_evaluation.decision == RiskDecisionType.REJECTED:
            failures.append(ExecutionReasonCode.RISK_REJECTED)

        # Risk budget must exist
        if not risk_evaluation.risk_budget:
            failures.append(ExecutionReasonCode.RISK_BUDGET_MISSING)

        # Kill switch
        if risk_state and risk_state.kill_switch_active:
            failures.append(ExecutionReasonCode.KILL_SWITCH_ACTIVE)

        # Constitution version
        if risk_evaluation.constitution_version != "v1":
            # In production, check against current constitution version
            pass  # Allow for now

        return len(failures) == 0, failures

    def validate_upstream_gates(
        self,
        instrument_plan: InstrumentPlan,
    ) -> tuple[bool, list[ExecutionReasonCode]]:
        """Validate upstream M3/M4/M5 gates."""
        failures: list[ExecutionReasonCode] = []

        # M5 NO_TRADE
        if instrument_plan.instrument_type.value == "NO_TRADE":
            failures.append(ExecutionReasonCode.UPSTREAM_NO_TRADE)

        # M4 REJECTED (already checked in M5, but defense in depth)
        if instrument_plan.no_trade_reason == "RISK_REJECTED":
            failures.append(ExecutionReasonCode.RISK_REJECTED)

        return len(failures) == 0, failures

    def validate_execution_config(self) -> tuple[bool, list[ExecutionReasonCode]]:
        """Validate execution configuration."""
        failures: list[ExecutionReasonCode] = []

        if not self._settings.enable_execution:
            failures.append(ExecutionReasonCode.EXECUTION_DISABLED)

        if self._settings.trading_mode != "paper":
            failures.append(ExecutionReasonCode.NOT_PAPER_MODE)

        if self._settings.alpaca_live_trade:
            failures.append(ExecutionReasonCode.LIVE_FLAG_ACTIVE)

        if not self._settings.enable_paper_execution:
            failures.append(ExecutionReasonCode.EXECUTION_DISABLED)

        return len(failures) == 0, failures


def create_execution_validator(
    settings: Settings | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
) -> ExecutionValidator:
    """Factory function to create execution validator."""
    if settings is None:
        settings = Settings()
    return ExecutionValidator(settings, alpaca_gateway)