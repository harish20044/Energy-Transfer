"""The simulator's public face: tick arithmetic, and one household's meter
reading for one tick.

Every reading comes from `app.simulator.household.simulate_household_day` —
a full day simulated appliance by appliance under that date's Chennai
weather, cached, then read one slot at a time. Solar generation is shared
weather scaled by each house's own capacity (two houses with equal panels
always read identically, being under the same sky); consumption is each
family's own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.simulator.household import HouseholdDay, simulate_household_day
from app.simulator.scenarios import Scenario
from app.simulator.weather import MINUTES_PER_DAY, DayWeather, day_weather

__all__ = [
    "MINUTES_PER_DAY",
    "MeterReading",
    "date_for",
    "day_index",
    "hour_of_day",
    "household_day_for",
    "reading_for",
    "slot_of",
    "weather_for",
]


@dataclass(frozen=True, slots=True)
class MeterReading:
    consumption_kw: float
    generation_kw: float


def hour_of_day(tick_index: int, *, tick_minutes: int) -> float:
    return ((tick_index * tick_minutes) % MINUTES_PER_DAY) / 60.0


def day_index(tick_index: int, *, tick_minutes: int) -> int:
    return (tick_index * tick_minutes) // MINUTES_PER_DAY


def slot_of(tick_index: int, *, tick_minutes: int) -> int:
    return ((tick_index * tick_minutes) % MINUTES_PER_DAY) // tick_minutes


def date_for(tick_index: int, *, start_date: date, tick_minutes: int) -> date:
    return start_date + timedelta(days=day_index(tick_index, tick_minutes=tick_minutes))


def weather_for(
    tick_index: int, *, start_date: date, tick_minutes: int, scenario: Scenario, seed: int
) -> DayWeather:
    day = date_for(tick_index, start_date=start_date, tick_minutes=tick_minutes)
    return day_weather(day, scenario, seed, tick_minutes)


def household_day_for(
    household_id: str,
    tick_index: int,
    *,
    member_count: int,
    solar_capacity_kwp: float,
    start_date: date,
    tick_minutes: int,
    scenario: Scenario,
    seed: int,
) -> HouseholdDay:
    day = date_for(tick_index, start_date=start_date, tick_minutes=tick_minutes)
    return simulate_household_day(
        household_id, member_count, solar_capacity_kwp, day, scenario, seed, tick_minutes
    )


def reading_for(
    household_id: str,
    tick_index: int,
    *,
    member_count: int,
    solar_capacity_kwp: float,
    start_date: date,
    tick_minutes: int,
    scenario: Scenario,
    seed: int,
) -> MeterReading:
    """Both sides of one household's meter for one tick."""
    household_day = household_day_for(
        household_id,
        tick_index,
        member_count=member_count,
        solar_capacity_kwp=solar_capacity_kwp,
        start_date=start_date,
        tick_minutes=tick_minutes,
        scenario=scenario,
        seed=seed,
    )
    slot = slot_of(tick_index, tick_minutes=tick_minutes)
    return MeterReading(
        consumption_kw=float(household_day.consumption_kw[slot]),
        generation_kw=float(household_day.generation_kw[slot]),
    )
