"""Feature engineering: only information a real forecaster could have, the
same row twice from the same inputs, and the family's own plans visible."""

from __future__ import annotations

from datetime import date

import pytest

from app.forecasting.features import (
    FEATURE_COLUMNS,
    HOURS_PER_DAY,
    TODAY_OFFSET,
    feature_row,
    features_for_household,
    hourly_window,
    target_index,
)
from app.simulator.family import HouseholdOverride
from app.simulator.scenarios import Scenario

pytestmark = pytest.mark.unit

SEED = 42
DAY = date(2026, 5, 15)


def _row(horizon: int = 3, override: HouseholdOverride | None = None) -> dict[str, float]:
    window = hourly_window(
        "h1", 4, 5.0, DAY, Scenario.AUTO, SEED, override=override or HouseholdOverride()
    )
    return feature_row(
        window,
        now_index=TODAY_OFFSET + 14,
        horizon_hours=horizon,
        family=features_for_household("h1", 4, SEED),
        seed=SEED,
    )


def test_feature_row_has_exactly_the_declared_columns() -> None:
    row = _row()
    assert set(row) == set(FEATURE_COLUMNS)
    assert "scenario" not in row  # never leak the truth being forecast


def test_feature_row_is_deterministic() -> None:
    assert _row() == _row()


def test_horizon_one_is_the_hour_starting_now() -> None:
    assert target_index(TODAY_OFFSET + 14, 1) == TODAY_OFFSET + 14
    assert _row(horizon=1)["hour_of_day"] == 14.0
    assert _row(horizon=12)["hour_of_day"] == 1.0  # 1 am the next day


def test_same_hour_yesterday_is_always_already_metered() -> None:
    for horizon in (1, 12, 24):
        target = target_index(TODAY_OFFSET + 14, horizon)
        assert target - HOURS_PER_DAY < TODAY_OFFSET + 14


def test_the_familys_what_ifs_are_visible_as_features() -> None:
    plans = HouseholdOverride(
        guests=2, away_from=15.0, away_to=18.0, work_from_home=True, panel_derate=0.5
    )
    row = _row(horizon=2, override=plans)  # 3 pm
    assert row["guests"] == 2.0
    assert row["family_away"] == 1.0
    assert row["wfh_today"] == 1.0
    assert row["solar_capacity_kwp"] == pytest.approx(2.5)


def test_temperature_forecast_is_near_but_not_exactly_the_truth() -> None:
    window = hourly_window("h1", 4, 5.0, DAY, Scenario.AUTO, SEED)
    row = _row(horizon=6)
    truth = float(window.temperature_c[target_index(TODAY_OFFSET + 14, 6)])
    assert row["temp_forecast_c"] != truth
    assert abs(row["temp_forecast_c"] - truth) < 5.0
