"""Synthetic meter readings: deterministic, scaled by household size and
solar capacity, and shaped the way real demand and generation actually are."""

from __future__ import annotations

import pytest

from app.simulator.profiles import consumption_kw, generation_kw, is_weekend
from app.simulator.scenarios import Scenario

pytestmark = pytest.mark.unit

_COMMON = {"tick_minutes": 15, "scenario": Scenario.CLEAR, "seed": 42}
_GEN_COMMON = {"tick_minutes": 15, "scenario": Scenario.CLEAR}


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
        assert generation_kw(tick_index=tick_index, solar_capacity_kwp=0.0, **_GEN_COMMON) == 0.0


def test_solar_generation_is_zero_at_night_and_positive_at_midday() -> None:
    ticks_per_day = 96  # 15-minute ticks
    midnight_tick = 0
    midday_tick = ticks_per_day // 2  # hour 12

    assert generation_kw(tick_index=midnight_tick, solar_capacity_kwp=5.0, **_GEN_COMMON) == 0.0
    assert generation_kw(tick_index=midday_tick, solar_capacity_kwp=5.0, **_GEN_COMMON) > 0.0


def test_larger_solar_capacity_generates_more_at_midday() -> None:
    midday_tick = 48
    small = generation_kw(tick_index=midday_tick, solar_capacity_kwp=2.0, **_GEN_COMMON)
    large = generation_kw(tick_index=midday_tick, solar_capacity_kwp=8.0, **_GEN_COMMON)
    assert large > small


def test_two_households_with_equal_capacity_generate_identically() -> None:
    """The core requirement: households share a location, so nothing but
    installed capacity may ever separate their solar output — there is no
    household id for this function to even accept."""
    for tick_index in (20, 48, 70):
        first = generation_kw(tick_index=tick_index, solar_capacity_kwp=5.0, **_GEN_COMMON)
        second = generation_kw(tick_index=tick_index, solar_capacity_kwp=5.0, **_GEN_COMMON)
        assert first == second


def test_generation_scales_exactly_linearly_with_capacity() -> None:
    """Twice the panels, exactly twice the output — no per-household noise
    left to break the proportionality."""
    midday_tick = 48
    one_kwp = generation_kw(tick_index=midday_tick, solar_capacity_kwp=1.0, **_GEN_COMMON)
    four_kwp = generation_kw(tick_index=midday_tick, solar_capacity_kwp=4.0, **_GEN_COMMON)
    assert four_kwp == pytest.approx(one_kwp * 4)


def test_peak_output_never_exceeds_nameplate_capacity() -> None:
    """Real panels never deliver their full rated capacity in the field —
    even at the sunniest hour of the sunniest scenario, output must stay
    below nameplate."""
    for tick_index in range(0, 96, 2):
        output = generation_kw(
            tick_index=tick_index,
            solar_capacity_kwp=5.0,
            tick_minutes=15,
            scenario=Scenario.HEATWAVE,
        )
        assert output <= 5.0


def test_cloudy_scenario_generates_less_than_clear() -> None:
    midday_tick = 48
    clear = generation_kw(
        tick_index=midday_tick, solar_capacity_kwp=5.0, tick_minutes=15, scenario=Scenario.CLEAR
    )
    cloudy = generation_kw(
        tick_index=midday_tick, solar_capacity_kwp=5.0, tick_minutes=15, scenario=Scenario.CLOUDY
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
        assert generation_kw(tick_index=tick_index, solar_capacity_kwp=3.0, **_GEN_COMMON) >= 0.0
