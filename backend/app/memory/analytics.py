"""Analytics module for M8 - Calibration, Similarity, Historical Context."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import TYPE_CHECKING, Optional, Any

from app.memory.models import (
    TradeRecord,
    TradeOutcome,
    TradeOutcomeType,
    ThesisOutcomeEvaluation,
    ThesisCorrectness,
    AgentPerformanceRecord,
    AgentStance,
    CommitteePerformanceSummary,
    CalibrationBucket,
    CalibrationSummary,
    CalibrationInsight,
    DisagreementBucket,
    TrendRegime,
    ExitReasonCategory,
    SimilarityComponent,
    SimilarTradeResult,
    HistoricalContext,
    RiskReductionAnalytics,
    RegimeAnalytics,
    DisagreementAnalytics,
    ExitReasonAnalytics,
    SignalAttribution,
    PerformanceSummary,
    DEFAULT_CALIBRATION_BUCKETS,
    DEFAULT_SIMILARITY_WEIGHTS,
    MIN_CALIBRATION_SAMPLE_SIZE,
)
from app.risk.models import RiskDecisionType

if TYPE_CHECKING:
    from app.memory.store import TradingMemoryStore
    from app.committee.models import CommitteeResult


class CalibrationEngine:
    """Deterministic confidence calibration engine."""

    def __init__(
        self,
        buckets: Optional[list[tuple[Decimal, Decimal]]] = None,
        min_sample_size: int = MIN_CALIBRATION_SAMPLE_SIZE,
    ) -> None:
        self.buckets = buckets or DEFAULT_CALIBRATION_BUCKETS
        self.min_sample_size = min_sample_size

    def compute_calibration(
        self,
        predictions: list[tuple[Decimal, bool]],  # (confidence, was_correct)
    ) -> CalibrationSummary:
        """Compute calibration from committee/agent predictions."""
        if not predictions:
            return CalibrationSummary(
                buckets=(),
                overall_insight=CalibrationInsight.INSUFFICIENT_DATA,
                total_samples=0,
            )

        # Filter out None confidences
        valid_predictions = [(c, o) for c, o in predictions if c is not None]
        total = len(valid_predictions)

        if total < self.min_sample_size:
            return CalibrationSummary(
                buckets=(),
                brier_score=self._brier_score(valid_predictions),
                overall_insight=CalibrationInsight.INSUFFICIENT_DATA,
                total_samples=total,
                min_sample_size=self.min_sample_size,
            )

        # Compute bucket statistics
        bucket_results = []
        for low, high in self.buckets:
            bucket_preds = [(c, o) for c, o in valid_predictions if low <= c < high]
            # Handle edge case for last bucket (include 1.0)
            if high == Decimal("1.0"):
                bucket_preds = [(c, o) for c, o in valid_predictions if low <= c <= high]

            count = len(bucket_preds)
            if count == 0:
                bucket_results.append(CalibrationBucket(
                    bucket_low=low,
                    bucket_high=high,
                    sample_count=0,
                ))
                continue

            count_dec = Decimal(str(count))
            mean_conf = sum(c for c, _ in bucket_preds) / count_dec
            accuracy = Decimal(str(sum(1 for _, o in bucket_preds if o))) / count_dec
            gap = mean_conf - accuracy

            bucket_results.append(CalibrationBucket(
                bucket_low=low,
                bucket_high=high,
                sample_count=count,
                mean_predicted_confidence=mean_conf,
                observed_success_rate=accuracy,
                calibration_gap=gap,
            ))

        # Overall Brier score
        brier = self._brier_score(valid_predictions)

        # ECE
        ece = self._ece(bucket_results, total)

        # Overall insight
        insight = self._determine_insight(bucket_results)

        return CalibrationSummary(
            buckets=tuple(bucket_results),
            brier_score=brier,
            ece=ece,
            min_sample_size=self.min_sample_size,
            overall_insight=insight,
            total_samples=total,
        )

    def _brier_score(self, predictions: list[tuple[Decimal, bool]]) -> Decimal:
        """Brier score = mean((predicted - actual)^2)."""
        if not predictions:
            return Decimal("0")
        total = sum((c - Decimal("1" if o else "0")) ** 2 for c, o in predictions)
        return total / Decimal(str(len(predictions)))

    def _ece(self, buckets: list[CalibrationBucket], total: int) -> Decimal:
        """Expected Calibration Error = weighted avg of |conf - acc|."""
        if total == 0:
            return Decimal("0")
        weighted_gaps = sum(
            (Decimal(str(b.sample_count)) / Decimal(str(total))) * abs(b.calibration_gap or Decimal("0"))
            for b in buckets
            if b.sample_count > 0
        )
        return Decimal(str(weighted_gaps))

    def _determine_insight(self, buckets: list[CalibrationBucket]) -> CalibrationInsight:
        """Determine overall calibration insight."""
        valid_buckets = [b for b in buckets if b.sample_count >= self.min_sample_size]
        if not valid_buckets:
            return CalibrationInsight.INSUFFICIENT_DATA

        # Average gap across valid buckets
        n_valid = Decimal(str(len(valid_buckets)))
        avg_gap = sum(b.calibration_gap or Decimal("0") for b in valid_buckets) / n_valid

        if avg_gap > Decimal("0.10"):
            return CalibrationInsight.OVERCONFIDENT
        elif avg_gap < Decimal("-0.10"):
            return CalibrationInsight.UNDERCONFIDENT
        else:
            return CalibrationInsight.WELL_CALIBRATED


class SimilarityEngine:
    """Deterministic historical trade similarity engine."""

    def __init__(
        self,
        weights: Optional[dict[str, Decimal]] = None,
    ) -> None:
        self.weights = weights or DEFAULT_SIMILARITY_WEIGHTS.copy()

    def find_similar(
        self,
        query_context: dict[str, Any],
        historical_trades: list[TradeRecord],
        k: int = 10,
    ) -> list[SimilarTradeResult]:
        """Find k most similar historical trades."""
        if not historical_trades:
            return []

        results = []
        for trade in historical_trades:
            if not trade.is_complete:
                continue

            components = self._compute_similarity_components(query_context, trade)
            score = sum(c.weight * c.score for c in components)
            if not isinstance(score, Decimal):
                score = Decimal(str(score))

            # Separate matching and differing
            matching = tuple(c for c in components if c.matching)
            differing = tuple(c for c in components if not c.matching)

            # Get outcome
            outcome = None
            if trade.realized_pnl is not None:
                if trade.realized_pnl > 0:
                    outcome = TradeOutcomeType.WIN
                elif trade.realized_pnl < 0:
                    outcome = TradeOutcomeType.LOSS
                else:
                    outcome = TradeOutcomeType.BREAKEVEN

            results.append(SimilarTradeResult(
                trade_id=trade.trade_id,
                similarity_score=score,
                matching_features=matching,
                differing_features=differing,
                outcome_type=outcome,
                return_pct=trade.return_pct,
                r_multiple=trade.r_multiple,
                direction=trade.direction,
                instrument_type=trade.instrument_type,
                committee_confidence=trade.committee_confidence,
                disagreement=trade.committee_disagreement,
            ))

        # Sort by similarity (descending), tie-break deterministically
        results.sort(key=lambda r: (-r.similarity_score, r.trade_id))
        return results[:k]

    def _compute_similarity_components(
        self,
        query: dict[str, Any],
        trade: TradeRecord,
    ) -> list[SimilarityComponent]:
        """Compute weighted similarity components."""
        components = []

        # Direction match
        dir_match = 1.0 if query.get("direction") == trade.direction else 0.0
        components.append(SimilarityComponent(
            name="direction_match",
            weight=self.weights.get("direction_match", Decimal("0.20")),
            score=Decimal(str(dir_match)),
            matching=dir_match == 1.0,
            details=f"Query: {query.get('direction')}, Trade: {trade.direction}",
        ))

        # Trend regime similarity
        regime_sim = self._regime_similarity(query.get("trend_regime"), trade)
        components.append(SimilarityComponent(
            name="trend_regime_similarity",
            weight=self.weights.get("trend_regime_similarity", Decimal("0.15")),
            score=regime_sim,
            matching=regime_sim > Decimal("0.5"),
            details=f"Regime similarity: {regime_sim:.2f}",
        ))

        # Volatility similarity (bucket-based)
        vol_sim = self._volatility_similarity(query.get("volatility_bucket"), trade)
        components.append(SimilarityComponent(
            name="volatility_similarity",
            weight=self.weights.get("volatility_similarity", Decimal("0.15")),
            score=vol_sim,
            matching=vol_sim > Decimal("0.5"),
            details=f"Vol similarity: {vol_sim:.2f}",
        ))

        # Momentum similarity
        mom_sim = self._momentum_similarity(query.get("momentum"), trade)
        components.append(SimilarityComponent(
            name="momentum_similarity",
            weight=self.weights.get("momentum_similarity", Decimal("0.10")),
            score=mom_sim,
            matching=mom_sim > Decimal("0.5"),
            details=f"Momentum similarity: {mom_sim:.2f}",
        ))

        # RSI similarity
        rsi_sim = self._rsi_similarity(query.get("rsi"), trade)
        components.append(SimilarityComponent(
            name="rsi_similarity",
            weight=self.weights.get("rsi_similarity", Decimal("0.10")),
            score=rsi_sim,
            matching=rsi_sim > Decimal("0.5"),
            details=f"RSI similarity: {rsi_sim:.2f}",
        ))

        # Confidence similarity
        conf_sim = self._confidence_similarity(query.get("committee_confidence"), trade)
        components.append(SimilarityComponent(
            name="confidence_similarity",
            weight=self.weights.get("confidence_similarity", Decimal("0.10")),
            score=conf_sim,
            matching=conf_sim > Decimal("0.5"),
            details=f"Confidence similarity: {conf_sim:.2f}",
        ))

        # Disagreement similarity
        dis_sim = self._disagreement_similarity(query.get("committee_disagreement"), trade)
        components.append(SimilarityComponent(
            name="disagreement_similarity",
            weight=self.weights.get("disagreement_similarity", Decimal("0.10")),
            score=dis_sim,
            matching=dis_sim > Decimal("0.5"),
            details=f"Disagreement similarity: {dis_sim:.2f}",
        ))

        # Instrument match
        inst_match = 1.0 if query.get("instrument_type") == trade.instrument_type else 0.0
        components.append(SimilarityComponent(
            name="instrument_match",
            weight=self.weights.get("instrument_match", Decimal("0.10")),
            score=Decimal(str(inst_match)),
            matching=inst_match == 1.0,
            details=f"Instrument: {query.get('instrument_type')} vs {trade.instrument_type}",
        ))

        return components

    def _regime_similarity(self, query_regime: Optional[str], trade: TradeRecord) -> Decimal:
        """Compute regime similarity (ordinal distance)."""
        if not query_regime:
            return Decimal("0.5")  # Neutral if unknown

        regime_order: dict[str, int] = {
            TrendRegime.STRONG_UP.value: 2,
            TrendRegime.UP.value: 1,
            TrendRegime.NEUTRAL.value: 0,
            TrendRegime.DOWN.value: -1,
            TrendRegime.STRONG_DOWN.value: -2,
        }

        q_val = regime_order.get(query_regime, 0)
        # Trade regime would need to be stored - use committee_disagreement as proxy for now
        t_val = 0  # Default neutral

        distance = abs(q_val - t_val)
        max_distance = 4
        return Decimal("1") - Decimal(str(distance)) / Decimal(str(max_distance))

    def _volatility_similarity(self, query_vol_bucket: Optional[str], trade: TradeRecord) -> Decimal:
        """Compute volatility similarity (bucket-based)."""
        if not query_vol_bucket or not trade.mae_pct:
            return Decimal("0.5")

        # Simple bucket comparison
        try:
            q_bucket = int(query_vol_bucket)
            # Trade vol bucket from MAE
            t_bucket = min(int(float(trade.mae_pct) * 100), 5)  # 0-5% buckets
            distance = abs(q_bucket - t_bucket)
            return Decimal("1") - Decimal(str(distance)) / Decimal("5")
        except (ValueError, TypeError):
            return Decimal("0.5")

    def _momentum_similarity(self, query_momentum: Optional[Decimal], trade: TradeRecord) -> Decimal:
        """Compute momentum similarity."""
        if query_momentum is None or trade.return_pct is None:
            return Decimal("0.5")

        # Compare momentum direction and magnitude
        q_sign = 1 if query_momentum > 0 else -1 if query_momentum < 0 else 0
        t_sign = 1 if trade.return_pct > 0 else -1 if trade.return_pct < 0 else 0

        if q_sign == t_sign:
            return Decimal("0.8")
        elif q_sign == 0 or t_sign == 0:
            return Decimal("0.5")
        else:
            return Decimal("0.2")

    def _rsi_similarity(self, query_rsi: Optional[Decimal], trade: TradeRecord) -> Decimal:
        """Compute RSI similarity."""
        if query_rsi is None:
            return Decimal("0.5")

        # Trade RSI not directly stored - use return as proxy
        # In real implementation, would store RSI at entry
        return Decimal("0.5")

    def _confidence_similarity(self, query_conf: Optional[Decimal], trade: TradeRecord) -> Decimal:
        """Compute committee confidence similarity."""
        if query_conf is None or trade.committee_confidence is None:
            return Decimal("0.5")

        diff = abs(query_conf - trade.committee_confidence)
        return Decimal("1") - diff

    def _disagreement_similarity(self, query_dis: Optional[str], trade: TradeRecord) -> Decimal:
        """Compute disagreement similarity."""
        if not query_dis or not trade.committee_disagreement:
            return Decimal("0.5")

        dis_order: dict[str, int] = {DisagreementBucket.LOW.value: 0, DisagreementBucket.MEDIUM.value: 1, DisagreementBucket.HIGH.value: 2}
        q_val = dis_order.get(query_dis, 1)
        t_val = dis_order.get(trade.committee_disagreement, 1)

        distance = abs(q_val - t_val)
        return Decimal("1") - Decimal(str(distance)) / Decimal("2")


class HistoricalContextProvider:
    """Read-only historical context provider for M3 integration."""

    def __init__(self, memory_store: TradingMemoryStore) -> None:
        self.memory_store = memory_store
        self.similarity_engine = SimilarityEngine()
        self.calibration_engine = CalibrationEngine()

    def get_context_for_trade(
        self,
        query_context: dict[str, Any],
        k: int = 10,
    ) -> HistoricalContext:
        """Get historical context for a prospective trade."""
        # Get all historical trades
        all_trades = self.memory_store.get_all_trade_records()

        # Find similar trades
        similar = self.similarity_engine.find_similar(query_context, all_trades, k)

        if not similar:
            return HistoricalContext(
                similar_trade_count=0,
                warnings=("No historical trades available",),
            )

        # Compute aggregate statistics
        outcomes = [s.outcome_type for s in similar if s.outcome_type]
        wins = sum(1 for o in outcomes if o == TradeOutcomeType.WIN)
        losses = sum(1 for o in outcomes if o == TradeOutcomeType.LOSS)
        total = len(outcomes)

        win_rate = Decimal(str(wins)) / Decimal(str(total)) if total > 0 else None

        # Directional accuracy from thesis evaluations would need separate query
        # For now, use win rate as proxy

        r_multiples = [s.r_multiple for s in similar if s.r_multiple is not None]
        mean_r = sum(r_multiples) / len(r_multiples) if r_multiples else None
        median_r = median(r_multiples) if r_multiples else None

        returns = [s.return_pct for s in similar if s.return_pct is not None]
        mean_return = sum(returns) / len(returns) if returns else None

        # MFE/MAE
        mfe_vals = [t.mfe_pct for t in all_trades if t.mfe_pct is not None]
        mae_vals = [t.mae_pct for t in all_trades if t.mae_pct is not None]
        mean_mfe = sum(mfe_vals) / len(mfe_vals) if mfe_vals else None
        mean_mae = sum(mae_vals) / len(mae_vals) if mae_vals else None

        # Holding period
        durations = [t.holding_duration_seconds for t in all_trades if t.holding_duration_seconds is not None]
        avg_holding = sum(durations) / len(durations) if durations else None

        # Calibration
        calibration = self._get_committee_calibration()

        # Agent stats
        agent_stats = self._get_agent_stats()

        # Warnings
        warnings = []
        if total < MIN_CALIBRATION_SAMPLE_SIZE:
            warnings.append(f"Only {total} similar trades (min {MIN_CALIBRATION_SAMPLE_SIZE} for strong conclusions)")

        return HistoricalContext(
            similar_trade_count=total,
            top_similar_trade_ids=tuple(s.trade_id for s in similar[:5]),
            win_rate=win_rate,
            directional_accuracy=win_rate,  # Proxy
            mean_r_multiple=Decimal(str(mean_r)) if mean_r is not None else None,
            median_r_multiple=Decimal(str(median_r)) if median_r is not None else None,
            mean_return_pct=Decimal(str(mean_return)) if mean_return is not None else None,
            mean_mfe_pct=Decimal(str(mean_mfe)) if mean_mfe is not None else None,
            mean_mae_pct=Decimal(str(mean_mae)) if mean_mae is not None else None,
            avg_holding_period_seconds=int(avg_holding) if avg_holding else None,
            committee_calibration=calibration,
            agent_stats=agent_stats,
            warnings=tuple(warnings),
        )

    def _get_committee_calibration(self) -> Optional[CalibrationSummary]:
        """Get latest committee calibration."""
        return self.memory_store.get_latest_calibration()

    def _get_agent_stats(self) -> dict[str, dict[str, Any]]:
        """Get agent performance statistics."""
        agents = ["QUANT", "BULL", "BEAR", "REGIME"]
        stats: dict[str, dict[str, Any]] = {}

        for agent in agents:
            records = self.memory_store.get_agent_history(agent)
            if not records:
                stats[agent] = {"trades_evaluated": 0}
                continue

            participated = [r for r in records if r.participated]
            abstained = [r for r in records if r.abstained]

            directional_correct = [r for r in participated if r.direction_correct is True]
            directional_incorrect = [r for r in participated if r.direction_correct is False]

            n_participated = Decimal(str(len(participated))) if participated else Decimal("0")
            stats[agent] = {
                "trades_evaluated": len(records),
                "participations": len(participated),
                "abstentions": len(abstained),
                "directional_accuracy": (
                    Decimal(str(len(directional_correct))) / n_participated if participated else None
                ),
                "mean_confidence": (
                    sum(r.confidence for r in participated) / n_participated if participated else None
                ),
            }

        return stats


class AnalyticsService:
    """Comprehensive analytics service for M8."""

    def __init__(self, memory_store: TradingMemoryStore) -> None:
        self.memory_store = memory_store
        self.calibration_engine = CalibrationEngine()
        self.similarity_engine = SimilarityEngine()

    def get_performance_summary(self) -> PerformanceSummary:
        """Generate comprehensive performance summary."""
        all_trades = self.memory_store.get_all_trade_records()

        if not all_trades:
            return PerformanceSummary(
                total_trades=0,
                committee=CommitteePerformanceSummary(),
                calibration=CalibrationSummary(
                    buckets=(),
                    overall_insight=CalibrationInsight.INSUFFICIENT_DATA,
                    total_samples=0,
                ),
            )

        # Committee performance
        completed = [t for t in all_trades if t.is_complete]
        wins = sum(1 for t in completed if t.realized_pnl and t.realized_pnl > 0)
        losses = sum(1 for t in completed if t.realized_pnl and t.realized_pnl < 0)
        breakevens = sum(1 for t in completed if t.realized_pnl == 0)

        r_multiples = [t.r_multiple for t in completed if t.r_multiple is not None]
        returns = [t.return_pct for t in completed if t.return_pct is not None]
        mfes = [t.mfe_pct for t in completed if t.mfe_pct is not None]
        maes = [t.mae_pct for t in completed if t.mae_pct is not None]
        durations = [t.holding_duration_seconds for t in completed if t.holding_duration_seconds is not None]
        confidences = [t.committee_confidence for t in completed if t.committee_confidence is not None]

        committee = CommitteePerformanceSummary(
            trade_count=len(completed),
            wins=wins,
            losses=losses,
            breakevens=breakevens,
            win_rate=Decimal(str(wins)) / Decimal(str(len(completed))) if completed else None,
            directional_accuracy=None,  # Would need thesis evaluations
            mean_r_multiple=sum(r_multiples) / Decimal(str(len(r_multiples))) if r_multiples else None,
            median_r_multiple=median(r_multiples) if r_multiples else None,
            mean_return_pct=sum(returns) / Decimal(str(len(returns))) if returns else None,
            mean_mfe_pct=sum(mfes) / Decimal(str(len(mfes))) if mfes else None,
            mean_mae_pct=sum(maes) / Decimal(str(len(maes))) if maes else None,
            avg_holding_period_seconds=int(sum(durations) / len(durations)) if durations else None,
            mean_committee_confidence=sum(confidences) / Decimal(str(len(confidences))) if confidences else None,
        )

        # Calibration - collect from agent performance
        calibration = self._compute_overall_calibration()

        # Disagreement analytics
        disagreement = self._compute_disagreement_analytics(completed)

        # Regime analytics
        regime = self._compute_regime_analytics(completed)

        # Exit reason analytics
        exit_reasons = self._compute_exit_reason_analytics(completed)

        # Risk reduction analytics
        risk_reduction = self._compute_risk_reduction_analytics(completed)

        # Signal attribution
        signal_attribution = self._compute_signal_attribution(completed)

        # Agent performance
        agent_perf = self._compute_agent_analytics()

        return PerformanceSummary(
            total_trades=len(all_trades),
            committee=committee,
            calibration=calibration,
            disagreement=disagreement,
            regime=regime,
            exit_reasons=exit_reasons,
            risk_reduction=risk_reduction,
            signal_attribution=signal_attribution,
            agent_performance=agent_perf,
        )

    def _compute_overall_calibration(self) -> CalibrationSummary:
        """Compute calibration from all agent predictions."""
        predictions = []
        agents = ["QUANT", "BULL", "BEAR", "REGIME"]

        for agent in agents:
            records = self.memory_store.get_agent_history(agent)
            for r in records:
                if r.calibration_target is not None:
                    predictions.append((r.confidence, r.calibration_target == 1))

        return self.calibration_engine.compute_calibration(predictions)

    def _compute_disagreement_analytics(self, trades: list[TradeRecord]) -> tuple[DisagreementAnalytics, ...]:
        """Compute outcomes by disagreement bucket."""
        buckets = defaultdict(list)

        for t in trades:
            if t.committee_disagreement:
                buckets[t.committee_disagreement].append(t)

        results = []
        for bucket_name, bucket_trades in buckets.items():
            r_multiples = [t.r_multiple for t in bucket_trades if t.r_multiple is not None]
            returns = [t.return_pct for t in bucket_trades if t.return_pct is not None]
            wins = sum(1 for t in bucket_trades if t.realized_pnl and t.realized_pnl > 0)

            results.append(DisagreementAnalytics(
                bucket=DisagreementBucket(bucket_name),
                count=len(bucket_trades),
                win_rate=Decimal(str(wins)) / Decimal(str(len(bucket_trades))) if bucket_trades else None,
                mean_r_multiple=sum(r_multiples) / Decimal(str(len(r_multiples))) if r_multiples else None,
                mean_return_pct=sum(returns) / Decimal(str(len(returns))) if returns else None,
            ))

        return tuple(results)

    def _compute_regime_analytics(self, trades: list[TradeRecord]) -> tuple[RegimeAnalytics, ...]:
        """Compute outcomes by trend regime."""
        # Regime not directly stored - would need entry context snapshot
        return ()

    def _compute_exit_reason_analytics(self, trades: list[TradeRecord]) -> tuple[ExitReasonAnalytics, ...]:
        """Compute outcomes by exit reason."""
        reason_map = defaultdict(list)

        for t in trades:
            for reason in t.exit_reason_codes:
                # Map to category
                category = self._categorize_exit_reason(reason)
                reason_map[category].append(t)

        results = []
        for category, category_trades in reason_map.items():
            r_multiples = [t.r_multiple for t in category_trades if t.r_multiple is not None]
            returns = [t.return_pct for t in category_trades if t.return_pct is not None]
            mfe_captures = [t.mfe_pct for t in category_trades if t.mfe_pct is not None]
            durations = [t.holding_duration_seconds for t in category_trades if t.holding_duration_seconds is not None]

            results.append(ExitReasonAnalytics(
                reason_category=category,
                count=len(category_trades),
                mean_r_multiple=sum(r_multiples) / Decimal(str(len(r_multiples))) if r_multiples else None,
                mean_return_pct=sum(returns) / Decimal(str(len(returns))) if returns else None,
                mean_mfe_capture=None,  # Would need exit quality
                mean_holding_duration_seconds=int(sum(durations) / len(durations)) if durations else None,
            ))

        return tuple(results)

    def _categorize_exit_reason(self, reason: str) -> ExitReasonCategory:
        """Map exit reason code to category."""
        hard_stops = {
            "HARD_STOP_TRIGGERED", "KILL_SWITCH", "MAX_LOSS_REACHED",
            "RISK_CONSTITUTION_VIOLATION", "OPTION_EXPIRY_APPROACHING",
            "MAX_HOLDING_PERIOD", "PROVIDER_RECONCILIATION_REQUIRED",
            "POSITION_MISMATCH", "MANUAL_CLOSE_DETECTED",
        }
        soft_exits = {
            "TAKE_PROFIT", "TRAILING_STOP_TRIGGERED",
            "THESIS_INVALIDATED", "TREND_REVERSAL",
            "MOMENTUM_REVERSAL", "VOLATILITY_SPIKE",
        }
        risk_reductions = {"PORTFOLIO_RISK_REDUCTION"}

        if reason in hard_stops:
            if reason == "HARD_STOP_TRIGGERED":
                return ExitReasonCategory.HARD_STOP
            elif reason == "KILL_SWITCH":
                return ExitReasonCategory.KILL_SWITCH
            elif reason == "MAX_LOSS_REACHED":
                return ExitReasonCategory.MAX_LOSS
            elif reason == "MAX_HOLDING_PERIOD":
                return ExitReasonCategory.MAX_HOLDING
            elif reason in ("THESIS_INVALIDATED", "TREND_REVERSAL", "MOMENTUM_REVERSAL", "VOLATILITY_SPIKE"):
                return ExitReasonCategory.THESIS_DETERIORATION
            elif reason == "PORTFOLIO_RISK_REDUCTION":
                return ExitReasonCategory.RISK_REDUCTION
            elif reason in ("PROVIDER_RECONCILIATION_REQUIRED", "POSITION_MISMATCH"):
                return ExitReasonCategory.RECONCILIATION
            elif reason == "MANUAL_CLOSE_DETECTED":
                return ExitReasonCategory.MANUAL
            return ExitReasonCategory.UNKNOWN
        elif reason in soft_exits:
            if reason == "TAKE_PROFIT":
                return ExitReasonCategory.TAKE_PROFIT
            elif reason == "TRAILING_STOP_TRIGGERED":
                return ExitReasonCategory.TRAILING_STOP
            return ExitReasonCategory.THESIS_DETERIORATION
        elif reason in risk_reductions:
            return ExitReasonCategory.RISK_REDUCTION
        return ExitReasonCategory.UNKNOWN

    def _compute_risk_reduction_analytics(self, trades: list[TradeRecord]) -> RiskReductionAnalytics:
        """Compare APPROVED vs REDUCED outcomes."""
        approved = [t for t in trades if t.risk_decision == RiskDecisionType.APPROVED.value]
        reduced = [t for t in trades if t.risk_decision == RiskDecisionType.REDUCED.value]

        def calc_stats(trade_list: list[TradeRecord]) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
            if not trade_list:
                return None, None, None, None
            r_multiples = [t.r_multiple for t in trade_list if t.r_multiple is not None]
            mae_vals = [t.mae_pct for t in trade_list if t.mae_pct is not None]
            mfe_vals = [t.mfe_pct for t in trade_list if t.mfe_pct is not None]
            wins = sum(1 for t in trade_list if t.realized_pnl and t.realized_pnl > 0)
            return (
                Decimal(str(wins)) / Decimal(str(len(trade_list))),
                sum(r_multiples) / Decimal(str(len(r_multiples))) if r_multiples else None,
                sum(mae_vals) / Decimal(str(len(mae_vals))) if mae_vals else None,
                sum(mfe_vals) / Decimal(str(len(mfe_vals))) if mfe_vals else None,
            )

        a_wr, a_mr, a_mae, a_mfe = calc_stats(approved)
        r_wr, r_mr, r_mae, r_mfe = calc_stats(reduced)

        return RiskReductionAnalytics(
            approved_count=len(approved),
            reduced_count=len(reduced),
            approved_win_rate=a_wr,
            reduced_win_rate=r_wr,
            approved_mean_r=a_mr,
            reduced_mean_r=r_mr,
            approved_mae=a_mae,
            reduced_mae=r_mae,
            approved_mfe=a_mfe,
            reduced_mfe=r_mfe,
        )

    def _compute_signal_attribution(self, trades: list[TradeRecord]) -> tuple[SignalAttribution, ...]:
        """Compute historical signal associations."""
        # Would need entry context with signal scores - placeholder
        signals = ["momentum", "trend", "volume", "volatility", "mean_reversion", "liquidity", "quality"]
        return tuple(SignalAttribution(signal_name=s, count=0) for s in signals)

    def _compute_agent_analytics(self) -> dict[str, dict[str, Any]]:
        """Compute per-agent analytics."""
        agents = ["QUANT", "BULL", "BEAR", "REGIME"]
        stats: dict[str, dict[str, Any]] = {}

        for agent in agents:
            records = self.memory_store.get_agent_history(agent)
            if not records:
                stats[agent] = {"trades_evaluated": 0}
                continue

            participated = [r for r in records if r.participated]
            abstained = [r for r in records if r.abstained]

            dir_correct = [r for r in participated if r.direction_correct is True]
            dir_incorrect = [r for r in participated if r.direction_correct is False]

            # Brier score
            predictions = [(r.confidence, r.calibration_target == 1) for r in participated if r.calibration_target is not None]
            brier = None
            if predictions:
                brier_val = sum((c - Decimal("1" if o else "0")) ** 2 for c, o in predictions) / Decimal(str(len(predictions)))
                brier = Decimal(str(brier_val))

            # Performance when agreeing/disagreeing with committee
            agreed = [r for r in participated if r.committee_agreement is True]
            disagreed = [r for r in participated if r.committee_agreement is False]
            agreed_correct = sum(1 for r in agreed if r.direction_correct is True)
            disagreed_correct = sum(1 for r in disagreed if r.direction_correct is True)

            n_participated = Decimal(str(len(participated))) if participated else Decimal("0")
            n_agreed = Decimal(str(len(agreed))) if agreed else Decimal("0")
            n_disagreed = Decimal(str(len(disagreed))) if disagreed else Decimal("0")

            stats[agent] = {
                "trades_evaluated": len(records),
                "participations": len(participated),
                "abstentions": len(abstained),
                "directional_accuracy": Decimal(str(len(dir_correct))) / n_participated if participated else None,
                "mean_confidence": sum(r.confidence for r in participated) / n_participated if participated else None,
                "brier_score": brier,
                "accuracy_when_agreeing": Decimal(str(agreed_correct)) / n_agreed if agreed else None,
                "accuracy_when_disagreeing": Decimal(str(disagreed_correct)) / n_disagreed if disagreed else None,
            }

        return stats