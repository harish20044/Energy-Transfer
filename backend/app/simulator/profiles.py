"""Per-household synthetic meter readings.

A household's demand is a smooth daily curve — morning and evening peaks —
scaled by its own member count, plus small per-household noise so no two
otherwise-identical houses draw exactly the same power (real behavioural
variation: different appliances, different habits).

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

from app.simulator.scenarios import Scenario, profile_for

MINUTES_PER_DAY = 24 * 60

# Per-member baseline draw (fridge, standby loads, ...), always-on.
BASE_LOAD_KW_PER_MEMBER = 0.15
MORNING_PEAK_KW_PER_MEMBER = 0.35
EVENING_PEAK_KW_PER_MEMBER = 0.55
WEEKEND_MIDDAY_KW_PER_MEMBER = 0.25

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
    """This household's power draw for one tick, in kW."""
    hour = hour_of_day(tick_index, tick_minutes=tick_minutes)
    weekend = is_weekend(tick_index, tick_minutes=tick_minutes)
    scenario_profile = profile_for(scenario)

    per_member = BASE_LOAD_KW_PER_MEMBER
    per_member += _bell(hour, center=7.5, width_hours=1.3, amplitude=MORNING_PEAK_KW_PER_MEMBER)
    per_member += _bell(
        hour,
        center=20.0 if weekend else 19.0,
        width_hours=2.2 if weekend else 1.8,
        amplitude=EVENING_PEAK_KW_PER_MEMBER * scenario_profile.evening_peak_boost,
    )
    if weekend:
        per_member += _bell(
            hour, center=13.0, width_hours=2.5, amplitude=WEEKEND_MIDDAY_KW_PER_MEMBER
        )

    noise = _noise(household_id, tick_index, seed, label="load", sigma=0.03 * member_count)
    total = member_count * per_member * scenario_profile.demand_factor + noise
    return max(0.0, total)


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
