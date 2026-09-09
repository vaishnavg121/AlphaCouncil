"""Risk Constitution - Centralized, versioned hard and soft limits for M4.

This is the single source of truth for all risk parameters.
NO AI can override these hard limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.risk.models import RiskReasonCode


@dataclass(frozen=True)
class HardLimit:
    """Hard gate limit - violation => REJECTED."""

    name: str
    reason_code: RiskReasonCode
    threshold: Decimal
    description: str


@dataclass(frozen=True)
class SoftLimit:
    """Soft reduction limit - violation => REDUCED (multiplicative factor)."""

    name: str
    reason_code: RiskReasonCode
    threshold: Decimal
    reduction_factor: Decimal  # 0.0 to 1.0, applied when threshold breached
    description: str


class RiskConstitution:
    """Versioned, immutable risk constitution.

    All limits are centralized here. Version changes require explicit migration.
    """

    VERSION: Final[str] = "v1.0.0"
    CREATED_AT: Final[str] = "2026-08-28"

    # ============================================================
    # BASE RISK PARAMETERS
    # ============================================================

    # Base capital at risk per trade as fraction of equity
    BASE_RISK_PER_TRADE: Final[Decimal] = Decimal("0.01")  # 1% of equity

    # Maximum position notional as fraction of equity
    MAX_POSITION_NOTIONAL_PCT: Final[Decimal] = Decimal("0.10")  # 10% of equity

    # Maximum gross exposure as fraction of equity
    MAX_GROSS_EXPOSURE_PCT: Final[Decimal] = Decimal("1.00")  # 100% of equity

    # Maximum net exposure as fraction of equity
    MAX_NET_EXPOSURE_PCT: Final[Decimal] = Decimal("0.50")  # 50% of equity

    # Maximum open positions
    MAX_OPEN_POSITIONS: Final[int] = 10

    # Maximum single symbol concentration as fraction of equity
    MAX_SYMBOL_CONCENTRATION_PCT: Final[Decimal] = Decimal("0.05")  # 5% of equity

    # Maximum group/sector concentration as fraction of equity
    MAX_GROUP_CONCENTRATION_PCT: Final[Decimal] = Decimal("0.20")  # 20% of equity

    # Maximum correlation redundancy (when implemented)
    MAX_CORRELATION: Final[Decimal] = Decimal("0.70")

    # ============================================================
    # HARD GATES (violation => REJECTED)
    # ============================================================

    HARD_GATES: Final[tuple[HardLimit, ...]] = (
        HardLimit(
            name="m3_no_trade",
            reason_code=RiskReasonCode.M3_NO_TRADE,
            threshold=Decimal("0"),  # Any NO_TRADE triggers
            description="M3 committee returned NO_TRADE decision",
        ),
        HardLimit(
            name="invalid_thesis",
            reason_code=RiskReasonCode.INVALID_THESIS,
            threshold=Decimal("0"),
            description="TradeThesis validation failed (missing required fields)",
        ),
        HardLimit(
            name="poor_data_quality",
            reason_code=RiskReasonCode.POOR_DATA_QUALITY,
            threshold=Decimal("0"),
            description="Market data quality is INSUFFICIENT or STALE",
        ),
        HardLimit(
            name="low_committee_confidence",
            reason_code=RiskReasonCode.LOW_COMMITTEE_CONFIDENCE,
            threshold=Decimal("0.60"),  # Minimum 60% committee confidence
            description="Committee confidence below minimum threshold",
        ),
        HardLimit(
            name="invalid_price",
            reason_code=RiskReasonCode.INVALID_PRICE,
            threshold=Decimal("0"),
            description="Reference price invalid (bid/ask spread too wide, price <= 0)",
        ),
        HardLimit(
            name="kill_switch",
            reason_code=RiskReasonCode.KILL_SWITCH_ACTIVE,
            threshold=Decimal("0"),
            description="Kill switch is active",
        ),
        HardLimit(
            name="daily_loss_limit",
            reason_code=RiskReasonCode.DAILY_LOSS_LIMIT,
            threshold=Decimal("0.03"),  # 3% daily loss limit
            description="Daily loss exceeds 3% of session-start equity",
        ),
        HardLimit(
            name="max_drawdown",
            reason_code=RiskReasonCode.MAX_DRAWDOWN,
            threshold=Decimal("0.10"),  # 10% max drawdown
            description="Current drawdown exceeds 10% from peak equity",
        ),
    )

    # ============================================================
    # SOFT REDUCTIONS (violation => REDUCED with multiplicative factor)
    # ============================================================

    SOFT_REDUCTIONS: Final[tuple[SoftLimit, ...]] = (
        # Volatility reduction - high vol => smaller position
        SoftLimit(
            name="volatility_reduction",
            reason_code=RiskReasonCode.VOLATILITY_REDUCTION,
            threshold=Decimal("0.03"),  # 3% daily vol threshold
            reduction_factor=Decimal("0.5"),  # Cut risk budget in half
            description="Realized volatility exceeds 3% daily, reduce position",
        ),
        # Liquidity reduction - low liquidity => smaller position
        SoftLimit(
            name="liquidity_reduction",
            reason_code=RiskReasonCode.LIQUIDITY_REDUCTION,
            threshold=Decimal("1000000"),  # $1M avg daily dollar volume
            reduction_factor=Decimal("0.5"),
            description="Average dollar volume below $1M, reduce position",
        ),
        # Confidence reduction - lower confidence => smaller position
        SoftLimit(
            name="confidence_reduction",
            reason_code=RiskReasonCode.CONFIDENCE_REDUCTION,
            threshold=Decimal("0.80"),  # Below 80% confidence
            reduction_factor=Decimal("0.75"),  # Reduce to 75%
            description="Committee confidence below 80%, proportional reduction",
        ),
        # Symbol concentration - already have position in symbol
        SoftLimit(
            name="symbol_concentration",
            reason_code=RiskReasonCode.SYMBOL_CONCENTRATION,
            threshold=Decimal("0.025"),  # 2.5% existing exposure
            reduction_factor=Decimal("0.5"),
            description="Existing symbol exposure exceeds 2.5% of equity",
        ),
        # Gross exposure limit
        SoftLimit(
            name="gross_exposure",
            reason_code=RiskReasonCode.GROSS_EXPOSURE,
            threshold=Decimal("0.80"),  # 80% of max gross
            reduction_factor=Decimal("0.5"),
            description="Gross exposure exceeds 80% of limit",
        ),
        # Net exposure limit
        SoftLimit(
            name="net_exposure",
            reason_code=RiskReasonCode.NET_EXPOSURE,
            threshold=Decimal("0.80"),  # 80% of max net
            reduction_factor=Decimal("0.5"),
            description="Net exposure exceeds 80% of limit",
        ),
        # Max positions limit
        SoftLimit(
            name="max_positions",
            reason_code=RiskReasonCode.MAX_POSITIONS,
            threshold=Decimal("8"),  # 8 positions (80% of 10)
            reduction_factor=Decimal("0.5"),
            description="Open positions exceed 8 (80% of max 10)",
        ),
        # Group concentration
        SoftLimit(
            name="group_concentration",
            reason_code=RiskReasonCode.GROUP_CONCENTRATION,
            threshold=Decimal("0.15"),  # 15% group exposure
            reduction_factor=Decimal("0.5"),
            description="Group/sector exposure exceeds 15% of equity",
        ),
        # Correlation redundancy
        SoftLimit(
            name="correlation_redundancy",
            reason_code=RiskReasonCode.CORRELATION_REDUNDANCY,
            threshold=Decimal("0.70"),
            reduction_factor=Decimal("0.5"),
            description="High correlation with existing positions",
        ),
    )

    # ============================================================
    # SIZING PARAMETERS
    # ============================================================

    # ATR multiplier for stop distance
    ATR_STOP_MULTIPLIER: Final[Decimal] = Decimal("2.0")

    # Minimum ATR stop distance as fraction of price (fallback)
    MIN_STOP_DISTANCE_PCT: Final[Decimal] = Decimal("0.02")  # 2%

    # Maximum ATR stop distance as fraction of price (cap)
    MAX_STOP_DISTANCE_PCT: Final[Decimal] = Decimal("0.10")  # 10%

    # Minimum shares for viable position
    MIN_SHARES: Final[int] = 1

    # Confidence reduction curve: linear from 1.0 at 100% to 0.5 at 60%
    CONFIDENCE_REDUCTION_SLOPE: Final[Decimal] = Decimal("1.25")  # (1.0 - 0.5) / (1.0 - 0.6)

    # Volatility reduction curve
    VOLATILITY_REDUCTION_SLOPE: Final[Decimal] = Decimal("0.5")  # Factor per unit over threshold

    # Liquidity reduction curve
    LIQUIDITY_REDUCTION_SLOPE: Final[Decimal] = Decimal("0.5")

    @classmethod
    def get_hard_gate(cls, name: str) -> HardLimit | None:
        """Get hard gate by name."""
        for gate in cls.HARD_GATES:
            if gate.name == name:
                return gate
        return None

    @classmethod
    def get_soft_limit(cls, name: str) -> SoftLimit | None:
        """Get soft limit by name."""
        for limit in cls.SOFT_REDUCTIONS:
            if limit.name == name:
                return limit
        return None

    @classmethod
    def all_hard_gate_names(cls) -> tuple[str, ...]:
        return tuple(g.name for g in cls.HARD_GATES)

    @classmethod
    def all_soft_limit_names(cls) -> tuple[str, ...]:
        return tuple(limit.name for limit in cls.SOFT_REDUCTIONS)


# Singleton instance for easy access
CONSTITUTION = RiskConstitution()
