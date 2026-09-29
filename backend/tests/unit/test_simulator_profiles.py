"""Chennai weather, rooftop PV and the appliance-level household model:
deterministic, physically sensible, and shared sky for every house."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.simulator.family import HouseholdOverride
from app.simulator.household import CATEGORIES, simulate_household_day
from app.simulator.profiles import date_for, day_index, hour_of_day, reading_for, slot_of
from app.simulator.scenarios import Scenario
from app.simulator.solar import sunrise_sunset_ist
from app.simulator.weather import day_weather

pytestmark = pytest.mark.unit

SEED = 42
MAY = date(2026, 5, 15)
JANUARY = date(2026, 1, 15)


def test_tick_arithmetic() -> None:
    assert hour_of_day(58, tick_minutes=15) == 14.5
    assert day_index(100, tick_minutes=15) == 1
    assert slot_of(100, tick_minutes=15) == 4
    assert date_for(96, start_date=MAY, tick_minutes=15) == date(2026, 5, 16)


def test_weather_is_deterministic() -> None:
    a = day_weather(MAY, Scenario.AUTO, SEED)
    b = day_weather(MAY, Scenario.AUTO, SEED)
    assert np.array_equal(a.pv_kw_per_kwp, b.pv_kw_per_kwp)
    assert a.t_max_c == b.t_max_c


def test_no_solar_between_sunset_and_sunrise() -> None:
    for day in (JANUARY, MAY, date(2026, 11, 20)):
        w = day_weather(day, Scenario.CLEAR, SEED)
        for i, value in enumerate(w.pv_kw_per_kwp):
            start, end = i * 0.25, (i + 1) * 0.25
            if end <= w.sunrise_h or start >= w.sunset_h:
                assert value == 0.0


def test_pv_never_exceeds_nameplate() -> None:
    assert day_weather(MAY, Scenario.HEATWAVE, SEED).pv_kw_per_kwp.max() <= 1.0


def test_rain_cuts_solar_and_heatwave_raises_temperature() -> None:
    clear = day_weather(MAY, Scenario.CLEAR, SEED)
    rainy = day_weather(MAY, Scenario.RAINY, SEED)
    heat = day_weather(MAY, Scenario.HEATWAVE, SEED)
    assert rainy.pv_kw_per_kwp.sum() < 0.6 * clear.pv_kw_per_kwp.sum()
    assert heat.t_max_c > clear.t_max_c + 3.0


def test_may_is_hotter_than_january() -> None:
    assert (
        day_weather(MAY, Scenario.AUTO, SEED).t_max_c
        > day_weather(JANUARY, Scenario.AUTO, SEED).t_max_c
    )


def test_chennai_sunrise_is_plausible() -> None:
    sunrise, sunset = sunrise_sunset_ist(date(2026, 5, 31))
    assert 5.5 < sunrise < 5.8  # published: 05:40
    assert 18.3 < sunset < 18.7


def test_equal_panels_read_identically_across_households() -> None:
    """One sky: only installed capacity separates two roofs' output."""
    a = simulate_household_day("h1", 4, 5.0, MAY, Scenario.AUTO, SEED)
    b = simulate_household_day("h9", 2, 5.0, MAY, Scenario.AUTO, SEED)
    assert np.array_equal(a.generation_kw, b.generation_kw)


def test_breakdown_sums_to_consumption() -> None:
    hd = simulate_household_day("h5", 6, 5.0, MAY, Scenario.AUTO, SEED)
    total = np.sum([hd.breakdown[c] for c in CATEGORIES], axis=0)
    assert np.allclose(total, hd.consumption_kw)
    assert (hd.consumption_kw >= 0).all()


def test_summer_nights_run_the_ac_and_winter_nights_mostly_dont() -> None:
    may_ac = sum(
        float(
            simulate_household_day(f"h{i}", 4, 5.0, MAY, Scenario.AUTO, SEED)
            .breakdown["cooling"]
            .sum()
        )
        for i in range(1, 11)
    )
    jan_ac = sum(
        float(
            simulate_household_day(f"h{i}", 4, 5.0, JANUARY, Scenario.AUTO, SEED)
            .breakdown["cooling"]
            .sum()
        )
        for i in range(1, 11)
    )
    assert may_ac > 5 * jan_ac


def test_an_empty_house_uses_far_less() -> None:
    home = simulate_household_day("h1", 4, 5.0, MAY, Scenario.AUTO, SEED)
    away = simulate_household_day(
        "h1", 4, 5.0, MAY, Scenario.AUTO, SEED, 15, HouseholdOverride(away_from=0.0, away_to=24.0)
    )
    assert away.consumption_kw.sum() < 0.3 * home.consumption_kw.sum()


def test_guests_add_load_and_dust_cuts_solar() -> None:
    base = simulate_household_day("h4", 2, 5.0, MAY, Scenario.AUTO, SEED)
    busy = simulate_household_day(
        "h4", 2, 5.0, MAY, Scenario.AUTO, SEED, 15, HouseholdOverride(guests=2, panel_derate=0.3)
    )
    assert busy.consumption_kw.sum() > base.consumption_kw.sum()
    assert busy.generation_kw.sum() == pytest.approx(0.7 * base.generation_kw.sum())


def test_reading_for_matches_the_household_day() -> None:
    hd = simulate_household_day("h2", 3, 5.0, MAY, Scenario.AUTO, SEED)
    reading = reading_for(
        "h2",
        50,
        member_count=3,
        solar_capacity_kwp=5.0,
        start_date=MAY,
        tick_minutes=15,
        scenario=Scenario.AUTO,
        seed=SEED,
    )
    assert reading.consumption_kw == pytest.approx(float(hd.consumption_kw[50]))
    assert reading.generation_kw == pytest.approx(float(hd.generation_kw[50]))
