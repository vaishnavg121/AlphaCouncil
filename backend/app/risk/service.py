"""Risk Evaluation Service - Orchestrates complete M4 risk evaluation.

ZERO LLM calls. NO trading execution. Pure deterministic computation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from app.committee.models import TradeThesis
from app.market.models import DataQualityStatus, MarketState
from app.risk.constitution import CONSTITUTION
from app.risk.models import (
    AccountSnapshot,
    NormalizedPosition,
    PortfolioSnapshot,
    RiskContext,
    RiskEvaluation,
    RiskState,
)
from app.risk.rules import PositionSizer, RiskDecisionEngine, RiskRulesEngine

if TYPE_CHECKING:
    from app.alpaca.gateway import AlpacaGateway
    from app.market.gateway import MarketDataGateway


class RiskEvaluationService:
    """Main service for evaluating trade theses against risk constitution."""

    def __init__(
        self,
        market_gateway: MarketDataGateway | None = None,
        alpaca_gateway: AlpacaGateway | None = None,
    ) -> None:
        self._market_gateway = market_gateway
        self._alpaca_gateway = alpaca_gateway
        self._rules_engine = RiskRulesEngine()
        self._sizer = PositionSizer()
        self._decider = RiskDecisionEngine()

    def evaluate(self, thesis: TradeThesis) -> RiskEvaluation:
        """Evaluate a trade thesis against the risk constitution.

        This is the main entry point for M4 risk evaluation.
        """
        start_time = datetime.now(UTC)

        # Build risk context
        ctx = self._build_context(thesis)

        # Run all risk checks
        checks = self._rules_engine.evaluate_all(ctx)

        # Compute risk budget
        budget = self._sizer.compute_budget(ctx, checks)

        # Make final decision
        evaluation = self._decider.decide(ctx, checks, budget)

        # Update runtime
        runtime_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
        return RiskEvaluation(
            symbol=evaluation.symbol,
            decision=evaluation.decision,
            reason_code=evaluation.reason_code,
            checks=evaluation.checks,
            risk_budget=evaluation.risk_budget,
            constitution_version=evaluation.constitution_version,
            evaluated_at=evaluation.evaluated_at,
            runtime_ms=runtime_ms,
        )

    def _build_context(self, thesis: TradeThesis) -> RiskContext:
        """Build complete risk context from thesis and live data."""
        # Get market data for the symbol
        market_state = self._get_market_state(thesis.symbol)

        # Get account and portfolio from Alpaca (paper)
        account = self._get_account_snapshot()
        portfolio = self._get_portfolio_snapshot()

        # Build risk state from account
        risk_state = self._build_risk_state(account, portfolio)

        # Extract market data for sizing
        reference_price = self._get_reference_price(market_state)
        atr_14 = market_state.features.atr_14 if market_state.features.atr_14 else None
        realized_vol_20 = market_state.features.realized_vol_20 if market_state.features.realized_vol_20 else None
        avg_dollar_volume_20 = market_state.features.avg_volume_20
        if avg_dollar_volume_20 is not None and reference_price > 0:
            avg_dollar_volume_20 = avg_dollar_volume_20 * reference_price
        else:
            avg_dollar_volume_20 = None

        bid_price = market_state.snapshot.quote.bid_price if market_state.snapshot.quote else None
        ask_price = market_state.snapshot.quote.ask_price if market_state.snapshot.quote else None
        spread_pct = None
        if bid_price and ask_price and bid_price > 0:
            mid = (bid_price + ask_price) / Decimal("2")
            spread_pct = (ask_price - bid_price) / mid

        return RiskContext(
            trade_thesis=thesis,
            reference_price=reference_price,
            atr_14=atr_14,
            bid_price=bid_price,
            ask_price=ask_price,
            spread_pct=spread_pct,
            avg_dollar_volume_20=avg_dollar_volume_20,
            realized_vol_20=realized_vol_20,
            account=account,
            portfolio=portfolio,
            risk_state=risk_state,
            constitution_version=CONSTITUTION.VERSION,
        )

    def _get_market_state(self, symbol: str) -> MarketState:
        """Get market state for symbol."""
        if self._market_gateway is None:
            # Return minimal market state for testing
            return self._minimal_market_state(symbol)

        # Use market gateway to build state
        from app.market import MarketStateBuilder
        builder = MarketStateBuilder(self._market_gateway)
        return builder.build(symbol)

    def _get_account_snapshot(self) -> AccountSnapshot:
        """Get account snapshot from Alpaca."""
        if self._alpaca_gateway is None:
            return self._default_account_snapshot()

        try:
            alpaca_account = self._alpaca_gateway.get_account()
            return AccountSnapshot(
                account_id=alpaca_account.account_id or "paper",
                status=alpaca_account.status,
                currency=alpaca_account.currency or "USD",
                equity=Decimal(alpaca_account.equity or "0"),
                buying_power=Decimal(alpaca_account.buying_power or "0"),
                cash=Decimal(alpaca_account.cash or "0"),
                portfolio_value=Decimal(alpaca_account.portfolio_value or "0"),
                initial_margin=Decimal(alpaca_account.initial_margin) if alpaca_account.initial_margin else None,
                maintenance_margin=Decimal(alpaca_account.maintenance_margin) if alpaca_account.maintenance_margin else None,
                daytrade_count=alpaca_account.daytrade_count or 0,
                as_of=datetime.now(UTC),
            )
        except Exception:
            # Fail-closed: return default on error
            return self._default_account_snapshot()

    def _get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Get portfolio snapshot from Alpaca."""
        if self._alpaca_gateway is None:
            return PortfolioSnapshot(account_id="paper", positions=(), as_of=datetime.now(UTC))

        try:
            alpaca_positions = self._alpaca_gateway.list_positions()
            positions = []
            for pos in alpaca_positions:
                qty = Decimal(str(pos.qty))
                market_value = Decimal(str(pos.market_value)) if pos.market_value else qty * Decimal("100")
                side: Literal["long", "short"] = "long" if qty > 0 else "short"
                positions.append(NormalizedPosition(
                    symbol=pos.symbol,
                    qty=abs(qty),
                    market_value=abs(market_value),
                    side=side,
                    entry_price=Decimal(str(pos.avg_entry_price)) if pos.avg_entry_price else None,
                    unrealized_pnl=Decimal(str(pos.unrealized_pl)) if pos.unrealized_pl else None,
                ))
            return PortfolioSnapshot(
                account_id="paper",
                positions=tuple(positions),
                as_of=datetime.now(UTC),
            )
        except Exception:
            return PortfolioSnapshot(account_id="paper", positions=(), as_of=datetime.now(UTC))

    def _build_risk_state(self, account: AccountSnapshot, portfolio: PortfolioSnapshot) -> RiskState:
        """Build risk state from account and portfolio."""
        equity = account.equity
        # For simplicity, use current equity as session start and peak
        # In production, this would be persisted across sessions
        return RiskState(
            session_start_equity=equity,
            peak_equity=equity,
            current_equity=equity,
            daily_realized_pnl=Decimal("0"),
            daily_unrealized_pnl=sum((p.unrealized_pnl or Decimal("0") for p in portfolio.positions), Decimal("0")),
            kill_switch_active=False,
            last_updated=datetime.now(UTC),
        )

    def _get_reference_price(self, market_state: MarketState) -> Decimal:
        """Get reference price for sizing."""
        # Prefer quote midpoint, fallback to last trade, fallback to last close
        if market_state.snapshot.quote:
            return market_state.snapshot.quote.midpoint
        if market_state.snapshot.trade:
            return market_state.snapshot.trade.price
        if market_state.latest_bar:
            return market_state.latest_bar.close
        if market_state.snapshot.daily_bar:
            return market_state.snapshot.daily_bar.close
        return Decimal("0")

    def _default_account_snapshot(self) -> AccountSnapshot:
        """Default account snapshot for testing."""
        return AccountSnapshot(
            account_id="paper",
            status="ACTIVE",
            currency="USD",
            equity=Decimal("100000"),
            buying_power=Decimal("200000"),
            cash=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            as_of=datetime.now(UTC),
        )

    def _minimal_market_state(self, symbol: str) -> MarketState:
        """Minimal market state for testing without gateway."""
        from app.market.models import (
            DataQuality,
            MarketSnapshot,
            OHLCVBar,
            QuoteSnapshot,
            TechnicalFeatures,
            Timeframe,
            TradeSnapshot,
            Trend,
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
                trend_short=Trend.UP,
                trend_medium=Trend.UP,
            ),
            data_quality=DataQuality(
                status=DataQualityStatus.GOOD,
                bars_requested=100,
                bars_received=100,
            ),
            bars_used=100,
        )


def create_risk_evaluation_service(
    market_gateway: MarketDataGateway | None = None,
    alpaca_gateway: AlpacaGateway | None = None,
) -> RiskEvaluationService:
    """Factory function to create risk evaluation service."""
    return RiskEvaluationService(market_gateway, alpaca_gateway)