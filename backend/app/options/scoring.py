"""Option contract scoring for M5.

Deterministic scoring based on liquidity, spread, expiry, moneyness, and Greeks.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.options.filters import OptionFilterConfig
from app.options.models import (
    OptionDataQualityStatus,
    OptionMarketSnapshot,
    OptionType,
)
from app.risk.models import RiskBudget


class OptionScoringConfig(BaseModel):
    """Configuration for option scoring weights."""

    model_config = ConfigDict(frozen=True)

    # Component weights (must sum to 1.0)
    weight_liquidity: Decimal = Decimal("0.25")
    weight_spread: Decimal = Decimal("0.20")
    weight_expiry: Decimal = Decimal("0.15")
    weight_moneyness: Decimal = Decimal("0.15")
    weight_delta: Decimal = Decimal("0.10")
    weight_iv: Decimal = Decimal("0.10")
    weight_data_quality: Decimal = Decimal("0.05")

    # Scoring parameters
    target_dte: int = 45
    target_moneyness: Decimal = Decimal("1.0")  # ATM
    target_abs_delta: Decimal = Decimal("0.55")
    preferred_spread_pct: Decimal = Decimal("0.03")
    max_spread_pct: Decimal = Decimal("0.10")
    require_greeks: bool = False
    require_iv: bool = False

    # Quality thresholds
    min_score: Decimal = Decimal("40")  # Minimum score to be considered
    option_complexity_margin: Decimal = Decimal("5")  # Option must beat equity by this much


class OptionScorer:
    """Deterministic option contract scorer."""

    def __init__(self, config: OptionScoringConfig | None = None) -> None:
        self.config = config or OptionScoringConfig()

    def score_contract(
        self,
        snap: OptionMarketSnapshot,
        underlying_price: Decimal,
        filter_config: OptionFilterConfig,
    ) -> tuple[Decimal, tuple[str, ...]]:
        """Score a single option contract. Returns (score, reasons)."""
        if underlying_price <= 0:
            return Decimal("0"), ("invalid underlying price",)

        # Invalid quote => score 0
        if not snap.quote or not snap.quote.is_valid():
            return Decimal("0"), ("invalid quote",)

        reasons: list[str] = []
        scores: dict[str, Decimal] = {}

        # Liquidity score (0-100)
        liq_score, liq_reasons = self._score_liquidity(snap)
        scores["liquidity"] = liq_score
        reasons.extend(liq_reasons)

        # Spread score (0-100)
        spread_score, spread_reasons = self._score_spread(snap)
        scores["spread"] = spread_score
        reasons.extend(spread_reasons)

        # Expiry score (0-100)
        expiry_score, expiry_reasons = self._score_expiry(snap, filter_config)
        scores["expiry"] = expiry_score
        reasons.extend(expiry_reasons)

        # Moneyness score (0-100)
        moneyness_score, mon_reasons = self._score_moneyness(snap, underlying_price)
        scores["moneyness"] = moneyness_score
        reasons.extend(mon_reasons)

        # Delta score (0-100)
        delta_score, delta_reasons = self._score_delta(snap, filter_config)
        scores["delta"] = delta_score
        reasons.extend(delta_reasons)

        # IV score (0-100)
        iv_score, iv_reasons = self._score_iv(snap)
        scores["iv"] = iv_score
        reasons.extend(iv_reasons)

        # Data quality score (0-100)
        dq_score, dq_reasons = self._score_data_quality(snap)
        scores["data_quality"] = dq_score
        reasons.extend(dq_reasons)

        # Weighted total
        total = (
            scores["liquidity"] * self.config.weight_liquidity
            + scores["spread"] * self.config.weight_spread
            + scores["expiry"] * self.config.weight_expiry
            + scores["moneyness"] * self.config.weight_moneyness
            + scores["delta"] * self.config.weight_delta
            + scores["iv"] * self.config.weight_iv
            + scores["data_quality"] * self.config.weight_data_quality
        )

        # Round to 2 decimal places
        final_score = total.quantize(Decimal("0.01"))
        return final_score, tuple(reasons)

    def _score_liquidity(self, snap: OptionMarketSnapshot) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on bid/ask sizes and volume."""
        if not snap.quote or not snap.quote.is_valid():
            return Decimal("0"), ("no valid quote",)

        q = snap.quote
        # Simple scoring based on sizes
        bid_size = int(q.bid_size) if q.bid_size else 0
        ask_size = int(q.ask_size) if q.ask_size else 0
        total_size = bid_size + ask_size

        if total_size >= 100:
            score = Decimal("100")
        elif total_size >= 50:
            score = Decimal("80")
        elif total_size >= 10:
            score = Decimal("60")
        elif total_size >= 1:
            score = Decimal("40")
        else:
            score = Decimal("10")

        return score, (f"bid_size={bid_size} ask_size={ask_size}",)

    def _score_spread(self, snap: OptionMarketSnapshot) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on spread percentage."""
        if not snap.quote or not snap.quote.is_valid() or not snap.quote.spread_pct:
            return Decimal("0"), ("no valid spread",)

        spread_pct = snap.quote.spread_pct
        pref = self.config.preferred_spread_pct
        max_spread = self.config.max_spread_pct

        if spread_pct <= pref:
            score = Decimal("100")
        elif spread_pct <= max_spread:
            # Linear decay from 100 to 40
            ratio = (max_spread - spread_pct) / (max_spread - pref)
            score = Decimal("40") + ratio * Decimal("60")
        else:
            score = Decimal("0")

        return score, (f"spread={spread_pct:.2%}",)

    def _score_expiry(
        self,
        snap: OptionMarketSnapshot,
        filter_config: OptionFilterConfig,
    ) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on days to expiry."""
        dte = snap.contract.days_to_expiry
        target = self.config.target_dte

        if dte <= 0:
            return Decimal("0"), ("expired",)

        # Distance from target
        dist = abs(dte - target)

        if dist <= 5:
            score = Decimal("100")
        elif dist <= 15:
            score = Decimal("80")
        elif dte >= filter_config.min_dte and dte <= filter_config.max_dte:
            score = Decimal("60")
        else:
            score = Decimal("20")

        return score, (f"dte={dte}",)

    def _score_moneyness(
        self,
        snap: OptionMarketSnapshot,
        underlying_price: Decimal,
    ) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on moneyness closeness to ATM."""
        if underlying_price <= 0:
            return Decimal("0"), ("invalid underlying",)

        if snap.contract.option_type == OptionType.CALL:
            moneyness = underlying_price / snap.contract.strike_price
        else:
            moneyness = snap.contract.strike_price / underlying_price

        target = self.config.target_moneyness
        dist = abs(moneyness - target)

        if dist <= Decimal("0.02"):
            score = Decimal("100")
        elif dist <= Decimal("0.05"):
            score = Decimal("80")
        elif dist <= Decimal("0.10"):
            score = Decimal("60")
        else:
            score = Decimal("30")

        return score, (f"moneyness={moneyness:.2%}",)

    def _score_delta(
        self,
        snap: OptionMarketSnapshot,
        filter_config: OptionFilterConfig,
    ) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on delta closeness to target."""
        if not snap.greeks:
            if self.config.require_greeks:
                return Decimal("0"), ("greeks required but missing",)
            return Decimal("50"), ("no greeks",)

        abs_delta = abs(snap.greeks.delta)
        target = self.config.target_abs_delta
        dist = abs(abs_delta - target)

        if dist <= Decimal("0.05"):
            score = Decimal("100")
        elif dist <= Decimal("0.10"):
            score = Decimal("80")
        elif (
            abs_delta >= filter_config.hard_abs_delta_min
            and abs_delta <= filter_config.hard_abs_delta_max
        ):
            score = Decimal("50")
        else:
            score = Decimal("10")

        return score, (f"delta={abs_delta:.2f}",)

    def _score_iv(self, snap: OptionMarketSnapshot) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on implied volatility availability and reasonableness."""
        if not snap.implied_volatility:
            if self.config.require_iv:
                return Decimal("0"), ("iv required but missing",)
            return Decimal("50"), ("no iv",)

        iv = snap.implied_volatility
        if iv <= 0 or iv > Decimal("5"):  # > 500% IV is unreasonable
            return Decimal("20"), (f"unusual iv={iv:.2%}",)

        # Moderate IV is preferred
        if Decimal("0.15") <= iv <= Decimal("0.60"):
            score = Decimal("100")
        elif Decimal("0.10") <= iv <= Decimal("1.00"):
            score = Decimal("70")
        else:
            score = Decimal("40")

        return score, (f"iv={iv:.2%}",)

    def _score_data_quality(self, snap: OptionMarketSnapshot) -> tuple[Decimal, tuple[str, ...]]:
        """Score based on data quality status."""
        if snap.data_quality == OptionDataQualityStatus.GOOD:
            return Decimal("100"), ("data_quality=GOOD",)
        elif snap.data_quality == OptionDataQualityStatus.DEGRADED:
            return Decimal("60"), ("data_quality=DEGRADED",)
        else:
            return Decimal("20"), (f"data_quality={snap.data_quality}",)


def select_best_option(
    eligible: list[OptionMarketSnapshot],
    underlying_price: Decimal,
    risk_budget: RiskBudget,
    filter_config: OptionFilterConfig,
    scorer: OptionScorer | None = None,
) -> tuple[OptionMarketSnapshot | None, Decimal, tuple[str, ...]]:
    """Select the best option contract from eligible ones."""
    if not eligible:
        return None, Decimal("0"), ("no eligible contracts",)

    scorer = scorer or OptionScorer()

    best_snap: OptionMarketSnapshot | None = None
    best_score = Decimal("-1")
    best_reasons: tuple[str, ...] = ()

    for snap in eligible:
        score, reasons = scorer.score_contract(snap, underlying_price, filter_config)
        if score > best_score:
            best_score = score
            best_snap = snap
            best_reasons = reasons

    return best_snap, best_score, best_reasons