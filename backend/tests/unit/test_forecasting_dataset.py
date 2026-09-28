"""Synthetic training data generation: must be reproducible from its seed
(the same guarantee the rest of the simulator holds itself to), cover every
declared horizon, and never predict a negative reading."""

from __future__ import annotations

import pytest

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.features import HORIZONS_HOURS

pytestmark = pytest.mark.unit

_CONFIGS = (HouseholdConfig(household_id="h1", member_count=4, solar_capacity_kwp=5.0),)


def test_generation_is_deterministic_given_the_same_seed() -> None:
    rows_a = generate_training_rows(_CONFIGS, num_days=3, seed=42)
    rows_b = generate_training_rows(_CONFIGS, num_days=3, seed=42)

    assert rows_a == rows_b


def test_every_horizon_is_represented() -> None:
    rows = generate_training_rows(_CONFIGS, num_days=3, seed=42)
    horizons = {row["horizon_hours"] for row in rows}

    assert horizons == {float(h) for h in HORIZONS_HOURS}


def test_targets_are_never_negative() -> None:
    rows = generate_training_rows(_CONFIGS, num_days=3, seed=42)

    assert all(row["consumption_kw"] >= 0 for row in rows)
    assert all(row["generation_kw"] >= 0 for row in rows)


def test_a_second_household_produces_its_own_rows_too() -> None:
    configs = (
        HouseholdConfig(household_id="h1", member_count=4, solar_capacity_kwp=5.0),
        HouseholdConfig(household_id="h4", member_count=2, solar_capacity_kwp=5.0),
    )
    rows = generate_training_rows(configs, num_days=3, seed=42)
    single = generate_training_rows(_CONFIGS, num_days=3, seed=42)

    assert len(rows) == 2 * len(single)
