"""Feature engineering must never leak the ground-truth scenario, and must
build the same row twice given the same inputs — training and live
inference both depend on that."""

from __future__ import annotations

import pytest

from app.forecasting.features import FEATURE_COLUMNS, HourlyLags, feature_row, household_family

pytestmark = pytest.mark.unit

_LAGS = HourlyLags(
    lag_1h_consumption_kw=1.0,
    lag_1h_generation_kw=0.5,
    lag_2h_consumption_kw=1.2,
    lag_2h_generation_kw=0.3,
    lag_24h_consumption_kw=0.9,
    lag_24h_generation_kw=0.8,
)


def test_feature_row_has_exactly_the_declared_columns() -> None:
    family = household_family("h1", member_count=4, seed=42)
    row = feature_row(
        family=family,
        solar_capacity_kwp=5.0,
        target_hour_of_day=14.0,
        target_is_weekend=False,
        horizon_hours=2,
        lags=_LAGS,
    )

    assert set(row) == set(FEATURE_COLUMNS)
    assert "scenario" not in row  # never leak the ground truth being forecast


def test_feature_row_is_deterministic() -> None:
    family = household_family("h3", member_count=5, seed=42)
    kwargs = dict(
        family=family,
        solar_capacity_kwp=5.0,
        target_hour_of_day=7.5,
        target_is_weekend=True,
        horizon_hours=1,
        lags=_LAGS,
    )

    assert feature_row(**kwargs) == feature_row(**kwargs)


def test_member_count_feature_matches_the_generated_family_size() -> None:
    family = household_family("h5", member_count=6, seed=42)
    row = feature_row(
        family=family,
        solar_capacity_kwp=5.0,
        target_hour_of_day=10.0,
        target_is_weekend=False,
        horizon_hours=3,
        lags=_LAGS,
    )

    assert row["member_count"] == 6.0
