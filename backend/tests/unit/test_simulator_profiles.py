"""Synthetic meter readings: deterministic, scaled by household size and
solar capacity, and shaped the way real demand and generation actually are."""

from __future__ import annotations

import pytest

from app.simulator.profiles import consumption_kw, generation_kw, is_weekend
from app.simulator.scenarios import Scenario

pytestmark = pytest.mark.unit

_COMMON = {"tick_minutes": 15, "scenario": Scenario.CLEAR, "seed": 42}


def test_same_inputs_always_produce_the_same_reading() -> None:
    """Determinism: the only thing that should vary a reading is its inputs,
    never wall-clock time or process state."""
    first = consumption_kw("h1", tick_index=40, member_count=4, **_COMMON)
    second = consumption_kw("h1", tick_index=40, member_count=4, **_COMMON)
    assert first == second


def test_larger_households_consume_more() -> None:
    small = consumption_kw("h1", tick_index=40, member_count=2, **_COMMON)
    large = consumption_kw("h1", tick_index=40, member_count=8, **_COMMON)
    assert large > small


def test_a_household_with_no_solar_never_generates() -> None:
    for tick_index in range(0, 96, 4):
        assert (
            generation_kw(
                "h2", tick_index=tick_index, solar_capacity_kwp=0.0, **_COMMON
            )
            == 0.0
        )


def test_solar_generation_is_zero_at_night_and_positive_at_midday() -> None:
    ticks_per_day = 96  # 15-minute ticks
    midnight_tick = 0
    midday_tick = ticks_per_day // 2  # hour 12

    assert (
        generation_kw("h1", tick_index=midnight_tick, solar_capacity_kwp=5.0, **_COMMON) == 0.0
    )
    assert generation_kw("h1", tick_index=midday_tick, solar_capacity_kwp=5.0, **_COMMON) > 0.0


def test_larger_solar_capacity_generates_more_at_midday() -> None:
    midday_tick = 48
    small = generation_kw("h1", tick_index=midday_tick, solar_capacity_kwp=2.0, **_COMMON)
    large = generation_kw("h1", tick_index=midday_tick, solar_capacity_kwp=8.0, **_COMMON)
    assert large > small


def test_cloudy_scenario_generates_less_than_clear() -> None:
    midday_tick = 48
    clear = generation_kw(
        "h1", tick_index=midday_tick, solar_capacity_kwp=5.0, tick_minutes=15,
        scenario=Scenario.CLEAR, seed=42,
    )
    cloudy = generation_kw(
        "h1", tick_index=midday_tick, solar_capacity_kwp=5.0, tick_minutes=15,
        scenario=Scenario.CLOUDY, seed=42,
    )
    assert cloudy < clear


def test_weekend_is_a_fixed_but_recurring_pattern() -> None:
    ticks_per_day = 96
    weekday_flags = [is_weekend(day * ticks_per_day, tick_minutes=15) for day in range(14)]
    # Exactly 2 of every 7 simulated days are weekend, twice over in 14 days.
    assert weekday_flags.count(True) == 4


def test_readings_are_never_negative() -> None:
    for tick_index in range(0, 96, 3):
        assert consumption_kw("h1", tick_index=tick_index, member_count=1, **_COMMON) >= 0.0
        assert (
            generation_kw("h1", tick_index=tick_index, solar_capacity_kwp=3.0, **_COMMON) >= 0.0
        )
