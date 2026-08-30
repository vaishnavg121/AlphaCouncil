"""Main instrument selection service for M5.

Orchestrates equity and option planning, compares alternatives,
and produces final InstrumentPlan.
"""

from __future__ import annotations

from decimal import Decimal

from app.committee.models import TradeThesis
from app.core.config import Settings
from app.instruments.models import (
    EquityInstrumentPlan,
    InstrumentPlan,
    InstrumentType,
    OptionInstrumentPlan,
    OptionRejectionSummary,
)
from app.instruments.stock import EquityPlanner
from app.market.models import MarketState
from app.options.filters import OptionFilterConfig, apply_option_filters
from app.options.gateway import OptionDataGateway
from app.options.scoring import OptionScorer, OptionScoringConfig, select_best_option
from app.options.sizing import OptionSizer
from app.risk.models import RiskDecisionType, RiskEvaluation


def _build_filter_config(settings: Settings) -> OptionFilterConfig:
    return OptionFilterConfig(
        min_dte=settings.option_min_dte,
        target_dte_min=settings.option_target_dte_min,
        target_dte_max=settings.option_target_dte_max,
        max_dte=settings.option_max_dte,
        min_moneyness_pct=Decimal(str(settings.option_min_moneyness_pct)),
        max_moneyness_pct=Decimal(str(settings.option_max_moneyness_pct)),
        target_abs_delta_min=Decimal(str(settings.option_target_abs_delta_min)),
        target_abs_delta_max=Decimal(str(settings.option_target_abs_delta_max)),
        hard_abs_delta_min=Decimal(str(settings.option_hard_abs_delta_min)),
        hard_abs_delta_max=Decimal(str(settings.option_hard_abs_delta_max)),
        max_spread_pct=Decimal(str(settings.option_max_spread_pct)),
        preferred_spread_pct=Decimal(str(settings.option_preferred_spread_pct)),
        max_option_contracts_per_plan=settings.option_max_contracts_per_plan,
        require_greeks=settings.option_require_greeks,
        require_iv=settings.option_require_iv,
    )


def _build_scoring_config(settings: Settings) -> OptionScoringConfig:
    return OptionScoringConfig(
        min_score=Decimal(str(settings.option_min_instrument_score)),
        option_complexity_margin=Decimal(str(settings.option_complexity_margin)),
    )


class InstrumentSelectorService:
    """Main M5 instrument selection service.

    ZERO LLM calls. Pure deterministic computation.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        option_gateway: OptionDataGateway | None = None,
        equity_planner: EquityPlanner | None = None,
        option_sizer: OptionSizer | None = None,
        option_scorer: OptionScorer | None = None,
        options_enabled: bool | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._option_gateway = option_gateway
        self._equity_planner = equity_planner or EquityPlanner()
        self._option_sizer = option_sizer or OptionSizer()
        self._option_scorer = option_scorer or OptionScorer()
        self._filter_config = _build_filter_config(self._settings)
        self._scoring_config = _build_scoring_config(self._settings)
        self._options_enabled = options_enabled if options_enabled is not None else self._settings.options_enabled

    def select(
        self,
        trade_thesis: TradeThesis,
        risk_evaluation: RiskEvaluation,
        market_state: MarketState,
    ) -> InstrumentPlan:
        """Select the best instrument for a trade thesis.

        Returns InstrumentPlan with STOCK, OPTION, or NO_TRADE.
        """
        # M4 Gate - immediate rejection if M4 rejected
        if risk_evaluation.decision == RiskDecisionType.REJECTED:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.NO_TRADE,
                underlying_symbol=trade_thesis.symbol,
                risk_evaluation_id=None,
                no_trade_reason="RISK_REJECTED",
                warnings=("M4 RiskEvaluation was REJECTED",),
            )

        # Validate risk budget exists
        if not risk_evaluation.risk_budget:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.NO_TRADE,
                underlying_symbol=trade_thesis.symbol,
                no_trade_reason="MISSING_RISK_BUDGET",
                warnings=("RiskEvaluation has no RiskBudget",),
            )

        # Validate thesis direction
        if trade_thesis.proposed_direction.value not in ("BULLISH", "BEARISH"):
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.NO_TRADE,
                underlying_symbol=trade_thesis.symbol,
                no_trade_reason="INVALID_THESIS",
                warnings=("Invalid thesis direction",),
            )

        # Build equity alternative
        equity_plan = self._build_equity_plan(trade_thesis, risk_evaluation, market_state)
        equity_eligible = equity_plan is not None

        # Build option alternative
        option_plan, option_rejections = self._build_option_plan(
            trade_thesis, risk_evaluation, market_state
        )
        option_eligible = option_plan is not None

        # Compare and select
        final_plan = self._select_instrument(
            trade_thesis,
            risk_evaluation,
            market_state,
            equity_plan,
            option_plan,
            option_rejections,
        )

        return final_plan

    def _build_equity_plan(
        self,
        trade_thesis: TradeThesis,
        risk_evaluation: RiskEvaluation,
        market_state: MarketState | None,
    ) -> EquityInstrumentPlan | None:
        """Build equity alternative if eligible."""
        if market_state is None:
            market_state = self._minimal_market_state(trade_thesis.symbol)

        # For bearish thesis, check shortability
        if trade_thesis.proposed_direction.value == "BEARISH":
            # In production, would check shortability from asset info
            # For now, allow short planning
            pass

        return self._equity_planner.calculate_plan(
            market_state,
            risk_evaluation,
            trade_thesis.proposed_direction.value,
        )

    def _minimal_market_state(self, symbol: str) -> MarketState:
        """Create minimal market state for synthetic testing."""
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.market.models import (
            DataQuality,
            DataQualityStatus,
            MarketSnapshot,
            MarketState,
            OHLCVBar,
            QuoteSnapshot,
            TechnicalFeatures,
            Timeframe,
            TradeSnapshot,
        )

        now = datetime.now(UTC)
        price = Decimal("100")
        return MarketState(
            symbol=symbol,
            as_of=now,
            timeframe=Timeframe.DAY,
            snapshot=MarketSnapshot(
                symbol=symbol,
                quote=QuoteSnapshot(symbol=symbol, timestamp=now, bid_price=price - Decimal("0.01"), ask_price=price + Decimal("0.01")),
                trade=TradeSnapshot(symbol=symbol, timestamp=now, price=price),
                daily_bar=OHLCVBar(symbol=symbol, timestamp=now, open=price, high=price * Decimal("1.01"), low=price * Decimal("0.99"), close=price, volume=1000000),
            ),
            latest_bar=OHLCVBar(symbol=symbol, timestamp=now, open=price, high=price * Decimal("1.01"), low=price * Decimal("0.99"), close=price, volume=1000000),
            features=TechnicalFeatures(
                atr_14=Decimal("2.0"),
                realized_vol_20=Decimal("0.02"),
                avg_volume_20=Decimal("1000000"),
            ),
            data_quality=DataQuality(
                status=DataQualityStatus.GOOD,
                bars_requested=100,
                bars_received=100,
            ),
            bars_used=100,
        )

    def _build_option_plan(
        self,
        trade_thesis: TradeThesis,
        risk_evaluation: RiskEvaluation,
        market_state: MarketState,
    ) -> tuple[OptionInstrumentPlan | None, OptionRejectionSummary]:
        """Build option alternative if eligible."""
        if not self._options_enabled:
            return None, OptionRejectionSummary()

        if not self._option_gateway:
            return None, OptionRejectionSummary(
                total_retrieved=0,
                other=0,
            )

        # Get option chain
        underlying_symbol = trade_thesis.symbol
        thesis_direction = trade_thesis.proposed_direction.value

        try:
            chain = self._option_gateway.get_option_chain(
                underlying_symbol,
            )
        except Exception:
            # Option data unavailable - equity may still be valid
            return None, OptionRejectionSummary(
                total_retrieved=0,
                other=1,  # Provider failure
            )

        if not chain:
            return None, OptionRejectionSummary(total_retrieved=0)

        # Filter by thesis direction (CALL for bullish, PUT for bearish)
        contract_type = "call" if thesis_direction == "BULLISH" else "put"
        directional_contracts = [c for c in chain if c.option_type.value.lower() == contract_type]

        if not directional_contracts:
            return None, OptionRejectionSummary(
                total_retrieved=len(chain),
                other=len(chain),
            )

        # Get reference price
        ref_price = self._get_underlying_price(market_state)
        if ref_price <= 0:
            return None, OptionRejectionSummary(
                total_retrieved=len(chain),
                other=len(chain),
            )

        # Get snapshots for all contracts
        contract_symbols = [c.symbol for c in directional_contracts]
        snapshots = self._option_gateway.get_option_snapshots(contract_symbols)

        # Apply filters
        risk_budget = risk_evaluation.risk_budget
        assert risk_budget is not None

        eligible_snapshots, filter_stats = apply_option_filters(
            directional_contracts,
            snapshots,
            ref_price,
            risk_budget,
            self._filter_config,
        )

        # Convert filter stats to rejection summary
        rejection_summary = OptionRejectionSummary(
            total_retrieved=filter_stats["total_retrieved"],
            expired_out_of_range=filter_stats["expired_out_of_range"],
            moneyness_out_of_range=filter_stats["moneyness_out_of_range"],
            delta_out_of_range=filter_stats["delta_out_of_range"],
            spread_too_wide=filter_stats["spread_too_wide"],
            premium_too_high=filter_stats["premium_too_high"],
            invalid_quote=filter_stats["invalid_quote"],
            zero_bid=filter_stats["zero_bid"],
            non_tradable=filter_stats["non_tradable"],
        )

        # Select best option
        best_snap, score, reasons = select_best_option(
            eligible_snapshots,
            ref_price,
            risk_budget,
            self._filter_config,
            self._option_scorer,
        )

        if not best_snap:
            return None, rejection_summary

        # Check minimum score threshold
        if score < self._scoring_config.min_score:
            return None, rejection_summary

        # Build option plan
        warnings = tuple(filter_stats.get("warnings", [])) if isinstance(filter_stats, dict) else ()
        option_plan = self._option_sizer.calculate_plan(
            best_snap,
            risk_budget,
            score,
            reasons,
            warnings=warnings,
        )

        return option_plan, rejection_summary

    def _select_instrument(
        self,
        trade_thesis: TradeThesis,
        risk_evaluation: RiskEvaluation,
        market_state: MarketState,
        equity_plan: EquityInstrumentPlan | None,
        option_plan: OptionInstrumentPlan | None,
        option_rejections: OptionRejectionSummary,
    ) -> InstrumentPlan:
        """Compare equity and option alternatives and select best."""
        equity_eligible = equity_plan is not None
        option_eligible = option_plan is not None

        # Both invalid
        if not equity_eligible and not option_eligible:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.NO_TRADE,
                underlying_symbol=trade_thesis.symbol,
                risk_evaluation_id=risk_evaluation.__dict__.get("_id"),
                no_trade_reason="NO_ELIGIBLE_EQUITY_PLAN" if not equity_eligible else "NO_ELIGIBLE_OPTION_CONTRACT",
                warnings=("No valid instrument plan found",),
            )

        # Only equity eligible
        if equity_eligible and not option_eligible:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.STOCK,
                underlying_symbol=trade_thesis.symbol,
                equity_plan=equity_plan,
                selection_reasons=("Only equity alternative eligible",),
                warnings=(f"Options: {option_rejections.total_rejected} contracts rejected",),
            )

        # Only option eligible
        if option_eligible and not equity_eligible:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.OPTION,
                underlying_symbol=trade_thesis.symbol,
                option_plan=option_plan,
                selection_reasons=("Only option alternative eligible",),
            )

        # Both eligible - compare scores
        equity_score = equity_plan.selection_score
        option_score = option_plan.selection_score

        # Apply complexity margin - option must beat equity by margin
        margin = self._scoring_config.option_complexity_margin
        effective_option_score = option_score - margin

        if effective_option_score > equity_score:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.OPTION,
                underlying_symbol=trade_thesis.symbol,
                option_plan=option_plan,
                selection_reasons=(
                    f"Option score {option_score:.1f} beats equity {equity_score:.1f} by margin",
                ),
            )
        elif equity_score > effective_option_score:
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.STOCK,
                underlying_symbol=trade_thesis.symbol,
                equity_plan=equity_plan,
                selection_reasons=(
                    f"Equity score {equity_score:.1f} beats option {option_score:.1f}",
                ),
            )
        else:
            # Tie - prefer simplicity (equity)
            return InstrumentPlan(
                symbol=trade_thesis.symbol,
                thesis_direction=trade_thesis.proposed_direction.value,
                instrument_type=InstrumentType.STOCK,
                underlying_symbol=trade_thesis.symbol,
                equity_plan=equity_plan,
                selection_reasons=(
                    f"Scores tied (equity={equity_score:.1f}, option={option_score:.1f}), preferring equity",
                ),
            )

    def _get_underlying_price(self, market_state: MarketState) -> Decimal:
        """Get reference price for underlying."""
        if market_state.snapshot.quote:
            return market_state.snapshot.quote.midpoint
        if market_state.snapshot.trade:
            return market_state.snapshot.trade.price
        if market_state.latest_bar:
            return market_state.latest_bar.close
        if market_state.snapshot.daily_bar:
            return market_state.snapshot.daily_bar.close
        return Decimal("0")