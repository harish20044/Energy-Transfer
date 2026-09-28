"""Per-household synthetic meter readings.

A household's demand comes from `app.simulator.family`: a generated family
of real ages occupying a real 4-bedroom house, each room's AC drawing power
only when someone is actually home to run it. Small per-household noise sits
on top so no two otherwise-identical houses draw exactly the same power
(real behavioural variation: different appliances, different habits).

Solar generation deliberately gets none of that per-household noise. Every
household in this simulation sits on the same feeder in the same
neighbourhood, so they all see the same sun and the same clouds at the same
instant — the only thing that should differ between two houses' solar output
is their own installed capacity. `generation_kw` is therefore a pure function
of the time of day, the scenario (the shared "weather"), and that one
household's kWp; two houses with equal capacity always read identically.

Deterministic given (household_id, tick_index, seed) for consumption; solar
needs no seed at all, since it has no randomness left to seed.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass

from app.simulator.family import (
    AC_CYCLING_FACTOR,
    AC_RATED_KW,
    BASE_LOAD_KW,
    PER_PRESENT_MEMBER_MISC_KW,
    generate_family,
    snapshot_occupancy,
)
from app.simulator.scenarios import Scenario, profile_for

MINUTES_PER_DAY = 24 * 60

SOLAR_PEAK_HOUR = 13.0
SOLAR_WIDTH_HOURS = 2.6
SOLAR_SUNRISE_HOUR = 6.0
SOLAR_SUNSET_HOUR = 19.0

# Real panels never deliver their STC-rated nameplate capacity in the field —
# module heating, inverter conversion, wiring and soiling losses take a real
# rooftop system down to roughly this fraction of nameplate on average across
# a day. Combined with the bell curve below, a 1 kWp system nets ~5 units/day
# on a clear day — the standard reference figure for Indian rooftop solar.
SOLAR_PERFORMANCE_RATIO = 0.78


@dataclass(frozen=True, slots=True)
class MeterReading:
    consumption_kw: float
    generation_kw: float


def _bell(hour: float, *, center: float, width_hours: float, amplitude: float) -> float:
    return amplitude * math.exp(-((hour - center) ** 2) / (2 * width_hours**2))


def hour_of_day(tick_index: int, *, tick_minutes: int) -> float:
    minutes_into_day = (tick_index * tick_minutes) % MINUTES_PER_DAY
    return minutes_into_day / 60.0


def day_index(tick_index: int, *, tick_minutes: int) -> int:
    return (tick_index * tick_minutes) // MINUTES_PER_DAY


def is_weekend(tick_index: int, *, tick_minutes: int) -> bool:
    """Every 6th and 7th simulated day of the run is a weekend — an arbitrary
    but fixed calendar, since the simulation has no real start date."""
    return day_index(tick_index, tick_minutes=tick_minutes) % 7 in (5, 6)


def _noise(household_id: str, tick_index: int, seed: int, *, label: str, sigma: float) -> float:
    digest = hashlib.sha256(f"{seed}:{household_id}:{tick_index}:{label}".encode()).hexdigest()
    rng = random.Random(int(digest[:16], 16))  # noqa: S311 -- deterministic synthetic data, not a secret
    return rng.gauss(0.0, sigma)


def consumption_kw(
    household_id: str,
    tick_index: int,
    *,
    member_count: int,
    tick_minutes: int,
    scenario: Scenario,
    seed: int,
) -> float:
    """This household's power draw for one tick, in kW — driven by who is
    actually home right now and which of the house's 4 bedroom ACs their
    presence is running, not a flat number scaled by headcount."""
    hour = hour_of_day(tick_index, tick_minutes=tick_minutes)
    weekend = is_weekend(tick_index, tick_minutes=tick_minutes)
    scenario_profile = profile_for(scenario)

    family = generate_family(household_id, member_count, seed)
    snapshot = snapshot_occupancy(family, hour, weekend, scenario_profile.demand_factor)

    ac_load_kw = sum(
        AC_RATED_KW * AC_CYCLING_FACTOR * room.ac_intensity for room in snapshot.rooms
    )
    misc_kw = BASE_LOAD_KW + snapshot.present_count * PER_PRESENT_MEMBER_MISC_KW

    noise = _noise(household_id, tick_index, seed, label="load", sigma=0.03 * member_count)
    return max(0.0, ac_load_kw + misc_kw + noise)


def generation_kw(
    tick_index: int,
    *,
    solar_capacity_kwp: float,
    tick_minutes: int,
    scenario: Scenario,
) -> float:
    """This household's rooftop solar output for one tick, in kW. Zero for a
    household with no panels (`solar_capacity_kwp == 0`) and at night.

    No household id, no seed: two households with the same installed
    capacity always read exactly the same value at the same tick, because in
    reality they're under the same sky.
    """
    if solar_capacity_kwp <= 0:
        return 0.0

    hour = hour_of_day(tick_index, tick_minutes=tick_minutes)
    if hour < SOLAR_SUNRISE_HOUR or hour > SOLAR_SUNSET_HOUR:
        return 0.0

    scenario_profile = profile_for(scenario)
    shape = _bell(hour, center=SOLAR_PEAK_HOUR, width_hours=SOLAR_WIDTH_HOURS, amplitude=1.0)
    return solar_capacity_kwp * shape * scenario_profile.solar_factor * SOLAR_PERFORMANCE_RATIO


def reading_for(
    household_id: str,
    tick_index: int,
    *,
    member_count: int,
    solar_capacity_kwp: float,
    tick_minutes: int,
    scenario: Scenario,
    seed: int,
) -> MeterReading:
    """Both sides of one household's meter for one tick."""
    return MeterReading(
        consumption_kw=consumption_kw(
            household_id,
            tick_index,
            member_count=member_count,
            tick_minutes=tick_minutes,
            scenario=scenario,
            seed=seed,
        ),
        generation_kw=generation_kw(
            tick_index,
            solar_capacity_kwp=solar_capacity_kwp,
            tick_minutes=tick_minutes,
            scenario=scenario,
        ),
    )
