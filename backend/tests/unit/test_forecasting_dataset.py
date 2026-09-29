"""Training data: reproducible from its seed, covering every horizon band a
session can ask for, and never predicting negative power."""

from __future__ import annotations

from datetime import date

import pytest

from app.forecasting.dataset import HouseholdConfig, generate_training_rows, override_for

pytestmark = pytest.mark.unit

_CONFIGS = (HouseholdConfig(household_id="h1", member_count=4, solar_capacity_kwp=5.0),)
_START = date(2025, 4, 1)


def _rows(configs: tuple[HouseholdConfig, ...] = _CONFIGS) -> list[dict[str, float]]:
    return generate_training_rows(configs, start=_START, num_days=2, seed=42)


def test_generation_is_deterministic_given_the_same_seed() -> None:
    assert _rows() == _rows()


def test_every_horizon_band_is_represented() -> None:
    horizons = {row["horizon_hours"] for row in _rows()}
    assert any(h <= 3 for h in horizons)
    assert any(4 <= h <= 8 for h in horizons)
    assert any(9 <= h <= 15 for h in horizons)
    assert any(16 <= h <= 24 for h in horizons)


def test_four_rows_per_forecast_origin() -> None:
    assert len(_rows()) == 2 * 24 * 4


def test_targets_are_never_negative() -> None:
    rows = _rows()
    assert all(row["consumption_kw"] >= 0 for row in rows)
    assert all(row["generation_kw"] >= 0 for row in rows)


def test_each_household_contributes_its_own_rows() -> None:
    two = (*_CONFIGS, HouseholdConfig(household_id="h4", member_count=2, solar_capacity_kwp=5.0))
    assert len(_rows(two)) == 2 * len(_rows())


def test_family_what_ifs_appear_in_training() -> None:
    overrides = [
        override_for(f"h{i}", date(2025, 1, 1 + d), 42) for i in range(1, 11) for d in range(28)
    ]
    assert any(o.guests for o in overrides)
    assert any(o.away_from is not None for o in overrides)
    assert any(o.work_from_home for o in overrides)
