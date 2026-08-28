"""Evidence packet builder for M3 committee.

Constructs structured, immutable evidence packets from M2 Candidates
with stable evidence IDs for agent grounding.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.committee.models import (
    EvidenceCategory,
    EvidenceItem,
    EvidencePacket,
    EvidenceSource,
)
from app.discovery.models import Candidate
from app.market.models import MarketState, SignalDirection


# Stable evidence ID constants
class EvidenceId:
    """Stable evidence IDs for agent grounding."""

    # Price
    E_PRICE = "E_PRICE"

    # Returns
    E_RET_1D = "E_RET_1D"
    E_RET_5D = "E_RET_5D"
    E_RET_20D = "E_RET_20D"

    # Momentum
    E_MOM_5D = "E_MOM_5D"
    E_MOM_20D = "E_MOM_20D"

    # Moving Averages
    E_SMA_20 = "E_SMA_20"
    E_SMA_50 = "E_SMA_50"
    E_EMA_20 = "E_EMA_20"
    E_EMA_50 = "E_EMA_50"

    # Trend Distances
    E_SMA20_DIST = "E_SMA20_DIST"
    E_SMA50_DIST = "E_SMA50_DIST"

    # RSI
    E_RSI_14 = "E_RSI_14"

    # ATR
    E_ATR_14 = "E_ATR_14"
    E_ATR_PCT = "E_ATR_PCT"

    # Volatility
    E_VOL_20 = "E_VOL_20"

    # Volume
    E_AVG_VOL_20 = "E_AVG_VOL_20"
    E_VOL_RATIO = "E_VOL_RATIO"
    E_VOL_ZSCORE = "E_VOL_ZSCORE"

    # Drawdown
    E_DRAWDOWN = "E_DRAWDOWN"

    # Trend
    E_TREND_SHORT = "E_TREND_SHORT"
    E_TREND_MEDIUM = "E_TREND_MEDIUM"

    # Liquidity
    E_DOLLAR_VOL = "E_DOLLAR_VOL"

    # Opportunity Score
    E_OPP_SCORE = "E_OPP_SCORE"
    E_OPP_DIR = "E_OPP_DIR"

    # Data Quality
    E_DQ_STATUS = "E_DQ_STATUS"
    E_DQ_BARS = "E_DQ_BARS"
    E_DQ_WARNINGS = "E_DQ_WARNINGS"

    # Discovery Reasons
    E_DISC_REASONS = "E_DISC_REASONS"


def _fmt_pct(value: Decimal | None) -> str:
    """Format decimal as percentage string."""
    if value is None:
        return "N/A"
    return f"{float(value):.2f}%"


def _fmt_decimal(value: Decimal | None, decimals: int = 2) -> str:
    """Format decimal with specified decimals."""
    if value is None:
        return "N/A"
    return f"{float(value):.{decimals}f}"


def _fmt_int(value: int | None) -> str:
    """Format integer."""
    if value is None:
        return "N/A"
    return str(value)


def _fmt_decimal_or_na(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return str(value)


def build_evidence_packet(candidate: Candidate) -> EvidencePacket:
    """Build structured evidence packet from M2 Candidate.

    Creates immutable evidence with stable IDs for agent grounding.
    """
    ms = candidate.market_state
    features = ms.features
    dq = ms.data_quality
    snapshot = ms.snapshot

    evidence_items = []

    # Current price
    price = snapshot.trade.price if snapshot.trade else (
        snapshot.quote.midpoint if snapshot.quote and snapshot.quote.is_valid() else
        (ms.latest_bar.close if ms.latest_bar else Decimal("0"))
    )
    evidence_items.append(EvidenceItem(
        id=EvidenceId.E_PRICE,
        category=EvidenceCategory.PRICE,
        label="Current Price",
        value=_fmt_decimal(price, 2),
        unit="USD",
        source=EvidenceSource.MARKET_SNAPSHOT,
    ))

    # Returns
    if features.return_1d is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_RET_1D,
            category=EvidenceCategory.RETURNS,
            label="1-Day Return",
            value=_fmt_pct(features.return_1d),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.return_5d is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_RET_5D,
            category=EvidenceCategory.RETURNS,
            label="5-Day Return",
            value=_fmt_pct(features.return_5d),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.return_20d is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_RET_20D,
            category=EvidenceCategory.RETURNS,
            label="20-Day Return",
            value=_fmt_pct(features.return_20d),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Momentum
    if features.momentum_5d is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_MOM_5D,
            category=EvidenceCategory.MOMENTUM,
            label="5-Day Momentum",
            value=_fmt_decimal(features.momentum_5d, 4),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.momentum_20d is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_MOM_20D,
            category=EvidenceCategory.MOMENTUM,
            label="20-Day Momentum",
            value=_fmt_decimal(features.momentum_20d, 4),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Moving Averages
    if features.sma_20 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_SMA_20,
            category=EvidenceCategory.TECHNICAL,
            label="SMA(20)",
            value=_fmt_decimal(features.sma_20, 2),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.sma_50 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_SMA_50,
            category=EvidenceCategory.TECHNICAL,
            label="SMA(50)",
            value=_fmt_decimal(features.sma_50, 2),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.ema_20 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_EMA_20,
            category=EvidenceCategory.TECHNICAL,
            label="EMA(20)",
            value=_fmt_decimal(features.ema_20, 2),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.ema_50 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_EMA_50,
            category=EvidenceCategory.TECHNICAL,
            label="EMA(50)",
            value=_fmt_decimal(features.ema_50, 2),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Trend Distances
    if features.distance_sma20_pct is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_SMA20_DIST,
            category=EvidenceCategory.TREND,
            label="Distance from SMA(20)",
            value=_fmt_pct(features.distance_sma20_pct),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.distance_sma50_pct is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_SMA50_DIST,
            category=EvidenceCategory.TREND,
            label="Distance from SMA(50)",
            value=_fmt_pct(features.distance_sma50_pct),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))

    # RSI
    if features.rsi_14 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_RSI_14,
            category=EvidenceCategory.TECHNICAL,
            label="RSI(14)",
            value=_fmt_decimal(features.rsi_14, 1),
            unit="",
            source=EvidenceSource.M1_FEATURE,
        ))

    # ATR
    if features.atr_14 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_ATR_14,
            category=EvidenceCategory.VOLATILITY,
            label="ATR(14)",
            value=_fmt_decimal(features.atr_14, 2),
            unit="USD",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.atr_pct is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_ATR_PCT,
            category=EvidenceCategory.VOLATILITY,
            label="ATR %",
            value=_fmt_pct(features.atr_pct),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Volatility
    if features.realized_vol_20 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_VOL_20,
            category=EvidenceCategory.VOLATILITY,
            label="Realized Vol(20)",
            value=_fmt_pct(features.realized_vol_20),
            unit="% (ann.)",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Volume
    if features.avg_volume_20 is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_AVG_VOL_20,
            category=EvidenceCategory.VOLUME,
            label="Avg Volume(20)",
            value=_fmt_int(int(features.avg_volume_20)),
            unit="shares",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.volume_ratio is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_VOL_RATIO,
            category=EvidenceCategory.VOLUME,
            label="Volume Ratio",
            value=f"{float(features.volume_ratio):.2f}x",
            unit="x",
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.volume_zscore is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_VOL_ZSCORE,
            category=EvidenceCategory.VOLUME,
            label="Volume Z-Score",
            value=_fmt_decimal(features.volume_zscore, 2),
            unit="σ",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Drawdown
    if features.current_drawdown is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_DRAWDOWN,
            category=EvidenceCategory.TECHNICAL,
            label="Current Drawdown",
            value=_fmt_pct(features.current_drawdown),
            unit="%",
            source=EvidenceSource.M1_FEATURE,
        ))

    # Trend
    if features.trend_short is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_TREND_SHORT,
            category=EvidenceCategory.TREND,
            label="Short Trend",
            value=features.trend_short,
            source=EvidenceSource.M1_FEATURE,
        ))
    if features.trend_medium is not None:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_TREND_MEDIUM,
            category=EvidenceCategory.TREND,
            label="Medium Trend",
            value=features.trend_medium,
            source=EvidenceSource.M1_FEATURE,
        ))

    # Liquidity
    if ms.snapshot.daily_bar is not None and ms.snapshot.daily_bar.volume is not None:
        dollar_vol = float(ms.snapshot.daily_bar.close) * ms.snapshot.daily_bar.volume
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_DOLLAR_VOL,
            category=EvidenceCategory.LIQUIDITY,
            label="Daily Dollar Volume",
            value=f"${dollar_vol/1e6:.1f}M",
            unit="USD",
            source=EvidenceSource.MARKET_SNAPSHOT,
        ))

    # Opportunity Score
    evidence_items.append(EvidenceItem(
        id=EvidenceId.E_OPP_SCORE,
        category=EvidenceCategory.DISCOVERY,
        label="Opportunity Score",
        value=_fmt_decimal(candidate.opportunity_score.total, 2),
        unit="/100",
        source=EvidenceSource.M2_DISCOVERY,
    ))
    evidence_items.append(EvidenceItem(
        id=EvidenceId.E_OPP_DIR,
        category=EvidenceCategory.DISCOVERY,
        label="Discovery Direction",
        value=candidate.opportunity_score.direction.value,
        source=EvidenceSource.M2_DISCOVERY,
    ))

    # Data Quality
    evidence_items.append(EvidenceItem(
        id=EvidenceId.E_DQ_STATUS,
        category=EvidenceCategory.DATA_QUALITY,
        label="Data Quality",
        value=str(dq.status),
        source=EvidenceSource.M1_FEATURE,
    ))
    evidence_items.append(EvidenceItem(
        id=EvidenceId.E_DQ_BARS,
        category=EvidenceCategory.DATA_QUALITY,
        label="Bars Received",
        value=f"{dq.bars_received}/{dq.bars_requested}",
        source=EvidenceSource.M1_FEATURE,
    ))
    if dq.warnings:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_DQ_WARNINGS,
            category=EvidenceCategory.DATA_QUALITY,
            label="Data Quality Warnings",
            value="; ".join(dq.warnings),
            source=EvidenceSource.M1_FEATURE,
        ))

    # Discovery Reasons
    if candidate.opportunity_score.reasons:
        evidence_items.append(EvidenceItem(
            id=EvidenceId.E_DISC_REASONS,
            category=EvidenceCategory.DISCOVERY,
            label="Discovery Reasons",
            value="; ".join(candidate.opportunity_score.reasons),
            source=EvidenceSource.M2_DISCOVERY,
        ))

    # Determine discovery direction string
    disc_dir = candidate.opportunity_score.direction.value

    return EvidencePacket(
        symbol=candidate.symbol,
        as_of=ms.as_of,
        candidate_rank=candidate.rank,
        opportunity_score=candidate.opportunity_score.total,
        discovery_direction=disc_dir,
        evidence=tuple(evidence_items),
        data_quality_status=str(dq.status),
        data_quality_warnings=dq.warnings,
        discovery_reasons=candidate.opportunity_score.reasons,
    )


def serialize_evidence_for_prompt(evidence: EvidencePacket) -> str:
    """Serialize evidence packet into concise prompt-friendly format."""
    lines = []

    lines.append(f"SYMBOL: {evidence.symbol}")
    lines.append(f"AS_OF: {evidence.as_of.isoformat()}")
    if evidence.candidate_rank:
        lines.append(f"RANK: #{evidence.candidate_rank}")
    if evidence.opportunity_score:
        lines.append(f"OPPORTUNITY_SCORE: {evidence.opportunity_score}/100")
    if evidence.discovery_direction:
        lines.append(f"DISCOVERY_DIRECTION: {evidence.discovery_direction}")

    lines.append("")
    lines.append("EVIDENCE:")

    # Group by category
    categories = [
        EvidenceCategory.PRICE,
        EvidenceCategory.RETURNS,
        EvidenceCategory.MOMENTUM,
        EvidenceCategory.TREND,
        EvidenceCategory.VOLATILITY,
        EvidenceCategory.VOLUME,
        EvidenceCategory.LIQUIDITY,
        EvidenceCategory.TECHNICAL,
        EvidenceCategory.DATA_QUALITY,
        EvidenceCategory.DISCOVERY,
    ]

    for cat in categories:
        items = evidence.get_evidence_by_category(cat)
        if items:
            for item in items:
                unit = f" {item.unit}" if item.unit else ""
                lines.append(f"  [{item.id}] {item.label}: {item.value}{unit}")

    if evidence.data_quality_status:
        lines.append("")
        lines.append(f"DATA_QUALITY: {evidence.data_quality_status}")
        if evidence.data_quality_warnings:
            for w in evidence.data_quality_warnings:
                lines.append(f"  WARNING: {w}")

    if evidence.discovery_reasons:
        lines.append("")
        lines.append("DISCOVERY_REASONS:")
        for r in evidence.discovery_reasons:
            lines.append(f"  - {r}")

    return "\n".join(lines)