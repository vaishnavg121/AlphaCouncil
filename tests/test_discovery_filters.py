from __future__ import annotations

"""Tests for hard filters."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.discovery.filters import FilterConfig, apply_hard_filters
from app.discovery.models import (
    RejectionReason,
    ScreeningObservation,
)


class TestFilterConfig:
    def test_valid_config(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=5_000_000.0,
            discovery_min_history_bars=50,
        )
        config = FilterConfig(settings)
        assert config.min_price == Decimal("5.0")
        assert config.min_avg_dollar_volume == Decimal("5000000.0")
        assert config.min_history_bars == 50

    def test_invalid_price_raises(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=-1.0,
            discovery_min_avg_dollar_volume=5_000_000.0,
            discovery_min_history_bars=50,
        )
        config = FilterConfig(settings)
        with pytest.raises(ValueError):
            config.validate()

    def test_invalid_dollar_volume_raises(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=-1.0,
            discovery_min_history_bars=50,
        )
        config = FilterConfig(settings)
        with pytest.raises(ValueError):
            config.validate()


class TestApplyHardFilters:
    def test_price_floor(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=10.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="LOWPRICE",
            as_of=datetime.now(UTC),
            price=Decimal("5.0"),  # Below min
            avg_volume_20=Decimal("1000000"),
            dollar_volume=Decimal("10000000"),
            bars_received=50,
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.PRICE_TOO_LOW

    def test_liquidity_floor(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=10_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="ILLIQUID",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            avg_volume_20=Decimal("50000"),
            dollar_volume=Decimal("5000000"),  # Below min
            bars_received=50,
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.LOW_LIQUIDITY

    def test_insufficient_history(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=50,
        )

        obs = ScreeningObservation(
            symbol="NEW",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            avg_volume_20=Decimal("1000000"),
            dollar_volume=Decimal("100000000"),
            bars_received=30,  # Below min
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.INSUFFICIENT_HISTORY

    def test_stale_data(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="STALE",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("1000000"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="STALE",
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.0"),
            rsi_14=Decimal("55"),
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.DATA_QUALITY_DEGRADED

    def test_invalid_data(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="INVALID",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            # Missing required fields for has_sufficient_data
            avg_volume_20=Decimal("1000000"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.INVALID_DATA

    def test_data_quality_degraded(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="DEGRADED",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            avg_volume_20=Decimal("1000000"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="DEGRADED",
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            volume=Decimal("1000000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.0"),
            rsi_14=Decimal("55"),
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 0
        assert len(rejections) == 1
        assert rejections[0].reason == RejectionReason.DATA_QUALITY_DEGRADED

    def test_valid_passes_all_filters(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        obs = ScreeningObservation(
            symbol="VALID",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("1200000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.0"),
            rsi_14=Decimal("55"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([obs], settings)
        assert len(eligible) == 1
        assert len(rejections) == 0
        assert eligible[0].symbol == "VALID"

    def test_multiple_observations(self) -> None:
        settings = Settings.model_construct(
            discovery_min_price=5.0,
            discovery_min_avg_dollar_volume=1_000_000.0,
            discovery_min_history_bars=20,
        )

        valid_obs = ScreeningObservation(
            symbol="VALID",
            as_of=datetime.now(UTC),
            price=Decimal("100.0"),
            return_5d=Decimal("0.02"),
            return_20d=Decimal("0.05"),
            avg_volume_20=Decimal("1000000"),
            volume=Decimal("1200000"),
            realized_vol_20=Decimal("0.25"),
            distance_sma20_pct=Decimal("2.0"),
            rsi_14=Decimal("55"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="GOOD",
        )

        invalid_obs = ScreeningObservation(
            symbol="INVALID",
            as_of=datetime.now(UTC),
            price=Decimal("1.0"),  # Too low
            avg_volume_20=Decimal("1000000"),
            dollar_volume=Decimal("100000000"),
            bars_received=50,
            data_quality_status="GOOD",
        )

        eligible, rejections = apply_hard_filters([valid_obs, invalid_obs], settings)
        assert len(eligible) == 1
        assert len(rejections) == 1
        assert eligible[0].symbol == "VALID"
        assert rejections[0].symbol == "INVALID"