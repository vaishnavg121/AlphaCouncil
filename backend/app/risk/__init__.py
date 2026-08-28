"""Risk module for M4 Deterministic Risk Constitution.

ZERO LLM calls. NO trading execution. Pure deterministic computation.
"""

from __future__ import annotations

from app.risk.constitution import CONSTITUTION, RiskConstitution
from app.risk.models import (
    AccountSnapshot,
    NormalizedPosition,
    PortfolioSnapshot,
    RiskBudget,
    RiskCheckResult,
    RiskContext,
    RiskDecisionType,
    RiskEvaluation,
    RiskReasonCode,
    RiskRuleType,
    RiskState,
)
from app.risk.rules import PositionSizer, RiskDecisionEngine, RiskRulesEngine
from app.risk.service import RiskEvaluationService, create_risk_evaluation_service

__all__ = [
    # Constitution
    "CONSTITUTION",
    "RiskConstitution",
    # Models
    "AccountSnapshot",
    "NormalizedPosition",
    "PortfolioSnapshot",
    "RiskBudget",
    "RiskCheckResult",
    "RiskContext",
    "RiskDecisionType",
    "RiskEvaluation",
    "RiskReasonCode",
    "RiskRuleType",
    "RiskState",
    # Rules
    "PositionSizer",
    "RiskDecisionEngine",
    "RiskRulesEngine",
    # Service
    "RiskEvaluationService",
    "create_risk_evaluation_service",
]