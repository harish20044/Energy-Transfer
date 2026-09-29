"""Pure feature engineering, shared by training and live inference — the same
function builds a training row and a live forecast's input, so there is no
train/serve skew by construction.

Every feature is something a real household forecaster could actually know
at the moment it forecasts, up to 24 hours ahead:

- **Calendar**: hour, weekday/weekend, season.
- **Who lives here**: how many people leave for work, work nights, stay home
  through the day, are students or elderly — fixed facts about the family.
- **The family's own plans** (the session's what-ifs): guests staying, the
  family out at the target hour, working from home today.
- **Weather forecast**: the target hour's temperature as a forecast would
  give it, with error that grows with lead time — never the true value.
- **Astronomy**: the clear-sky PV potential of the target hour for this
  roof (sun position is exactly predictable; only clouds aren't), scaled by
  the panels' known condition.
- **The meter's own history**: the last two hours, the same hour on the
  most recent metered day, and how cloudy the last daylight hours were.

Never used: the day's scenario label or its true cloudiness.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from app.simulator.family import (
    NO_OVERRIDE,
    Family,
    HouseholdOverride,
    Occupation,
    Role,
    generate_family,
)
from app.simulator.household import simulate_household_day
from app.simulator.scenarios import Scenario
from app.simulator.solar import FloatArray
from app.simulator.weather import day_weather

MAX_HORIZON_HOURS = 24
HORIZON_CHOICES: tuple[int, ...] = (4, 8, 12, 24)
HOURS_PER_DAY = 24
# An HourlyWindow spans the day before yesterday, yesterday, today and
# tomorrow; this is the index of today's midnight in it.
TODAY_OFFSET = 2 * HOURS_PER_DAY

FEATURE_COLUMNS: tuple[str, ...] = (
    "hour_of_day",
    "is_weekend",
    "horizon_hours",
    "season_sin",
    "season_cos",
    "member_count",
    "occupied_bedrooms",
    "away_workers",
    "night_shift",
    "daytime_home",
    "students",
    "elderly",
    "schedule_offset_hours",
    "guests",
    "family_away",
    "wfh_today",
    "solar_capacity_kwp",
    "temp_forecast_c",
    "clear_sky_pv_kw",
    "recent_clearness",
    "lag_1h_consumption_kw",
    "lag_1h_generation_kw",
    "lag_2h_consumption_kw",
    "lag_2h_generation_kw",
    "lag_day_consumption_kw",
    "lag_day_generation_kw",
)

TARGET_CONSUMPTION = "consumption_kw"
TARGET_GENERATION = "generation_kw"

# Temperature forecast error (deg C, 1 sigma) at 1 hour ahead, growing with
# lead time — roughly what a good day-ahead point forecast manages.
_TEMP_FORECAST_SIGMA_C = 0.6
_TEMP_FORECAST_SIGMA_PER_HOUR_C = 0.06
_MIN_CLEAR_SKY_KWH_FOR_CLEARNESS = 0.2


@dataclass(frozen=True, slots=True)
class FamilyFeatures:
    member_count: float
    occupied_bedrooms: float
    away_workers: float
    night_shift: float
    daytime_home: float
    students: float
    elderly: float
    schedule_offset_hours: float


def family_features(family: Family) -> FamilyFeatures:
    return FamilyFeatures(
        member_count=float(len(family.members)),
        occupied_bedrooms=float(family.occupied_bedrooms),
        # A hybrid worker is out on about half of weekdays.
        away_workers=family.count(Occupation.OFFICE) + 0.5 * family.count(Occupation.HYBRID),
        night_shift=float(family.count(Occupation.NIGHT_SHIFT)),
        daytime_home=float(family.count(Occupation.HOMEMAKER, Occupation.RETIRED)),
        students=float(family.count(Occupation.SCHOOL, Occupation.COLLEGE, Occupation.PRESCHOOL)),
        elderly=float(sum(1 for m in family.members if m.role is Role.GRANDPARENT)),
        schedule_offset_hours=family.schedule_offset_hours,
    )


def features_for_household(household_id: str, member_count: int, seed: int) -> FamilyFeatures:
    return family_features(generate_family(household_id, member_count, seed))


@dataclass(frozen=True, slots=True, eq=False)
class HourlyWindow:
    """Four consecutive days for one household, hour by hour (96 values
    each). Index `TODAY_OFFSET + h` is hour h of `today`."""

    today: date
    override: HouseholdOverride
    effective_kwp: float
    consumption_kw: FloatArray
    generation_kw: FloatArray
    temperature_c: FloatArray
    clear_sky_pv_kw: FloatArray


def _hourly(values: FloatArray, tick_minutes: int) -> FloatArray:
    per_hour = 60 // tick_minutes
    result: FloatArray = values.reshape(HOURS_PER_DAY, per_hour).mean(axis=1)
    return result


def hourly_window(
    household_id: str,
    member_count: int,
    solar_capacity_kwp: float,
    today: date,
    scenario: Scenario,
    seed: int,
    tick_minutes: int = 15,
    override: HouseholdOverride = NO_OVERRIDE,
    tomorrow_scenario: Scenario = Scenario.AUTO,
) -> HourlyWindow:
    """History days are always the climatological (AUTO) weather — a
    "what-if" applies to the day being planned, not the past. Tomorrow's
    weather is `tomorrow_scenario` (a live session running past midnight
    keeps its scenario; training uses climatology), and only the parts of
    today's override that carry over apply to it (guests staying, an outing
    past midnight, dusty panels)."""
    days = (
        (today - timedelta(days=2), Scenario.AUTO, override.history()),
        (today - timedelta(days=1), Scenario.AUTO, override.history()),
        (today, scenario, override),
        (today + timedelta(days=1), tomorrow_scenario, override.next_day()),
    )
    effective_kwp = solar_capacity_kwp * (1.0 - override.panel_derate)
    consumption, generation, temperature, clear_sky = [], [], [], []
    for day, day_scenario, day_override in days:
        household_day = simulate_household_day(
            household_id,
            member_count,
            solar_capacity_kwp,
            day,
            day_scenario,
            seed,
            tick_minutes,
            day_override,
        )
        consumption.append(_hourly(household_day.consumption_kw, tick_minutes))
        generation.append(_hourly(household_day.generation_kw, tick_minutes))
        temperature.append(_hourly(household_day.weather.temperature_c, tick_minutes))
        clear = day_weather(day, Scenario.CLEAR, seed, tick_minutes).pv_kw_per_kwp
        clear_sky.append(_hourly(clear, tick_minutes) * effective_kwp)
    return HourlyWindow(
        today=today,
        override=override,
        effective_kwp=effective_kwp,
        consumption_kw=np.concatenate(consumption),
        generation_kw=np.concatenate(generation),
        temperature_c=np.concatenate(temperature),
        clear_sky_pv_kw=np.concatenate(clear_sky),
    )


def _temperature_forecast_error(seed: int, target: date, hour: int, horizon: int) -> float:
    digest = hashlib.sha256(
        f"{seed}:tempfc:{target.isoformat()}:{hour}:{horizon}".encode()
    ).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "big"))
    sigma = _TEMP_FORECAST_SIGMA_C + _TEMP_FORECAST_SIGMA_PER_HOUR_C * (horizon - 1)
    return float(rng.normal(0.0, sigma))


def _clearness(window: HourlyWindow, lo: int, hi: int) -> float | None:
    clear = float(window.clear_sky_pv_kw[lo:hi].sum())
    if clear < _MIN_CLEAR_SKY_KWH_FOR_CLEARNESS:
        return None
    return float(window.generation_kw[lo:hi].sum()) / clear


def target_index(now_index: int, horizon_hours: int) -> int:
    """Horizon 1 is the hour starting now (the first one a session trades);
    horizon 24 the hour starting 23 hours later."""
    return now_index + horizon_hours - 1


def feature_row(
    window: HourlyWindow,
    *,
    now_index: int,
    horizon_hours: int,
    family: FamilyFeatures,
    seed: int,
) -> dict[str, float]:
    """One input row: forecasting hour `target_index(now_index, horizon)`
    from the vantage point of the start of `now_index` — only hours strictly
    before it have been metered. The same hour a day earlier is therefore
    always metered, even 24 hours ahead."""
    target = target_index(now_index, horizon_hours)
    day_offset = target // HOURS_PER_DAY - TODAY_OFFSET // HOURS_PER_DAY
    target_day = window.today + timedelta(days=day_offset)
    target_hour = target % HOURS_PER_DAY
    doy = target_day.timetuple().tm_yday
    override = window.override if day_offset == 0 else window.override.next_day()

    recent = _clearness(window, now_index - 2, now_index)
    if recent is None:
        # Night, or dawn: the last full daylight we have is yesterday's.
        yesterday = _clearness(window, TODAY_OFFSET - HOURS_PER_DAY, TODAY_OFFSET)
        recent = yesterday if yesterday is not None else 0.8

    lag_day = target - HOURS_PER_DAY
    return {
        "hour_of_day": float(target_hour),
        "is_weekend": float(target_day.weekday() >= 5),
        "horizon_hours": float(horizon_hours),
        "season_sin": math.sin(2 * math.pi * doy / 365.0),
        "season_cos": math.cos(2 * math.pi * doy / 365.0),
        "member_count": family.member_count,
        "occupied_bedrooms": family.occupied_bedrooms,
        "away_workers": family.away_workers,
        "night_shift": family.night_shift,
        "daytime_home": family.daytime_home,
        "students": family.students,
        "elderly": family.elderly,
        "schedule_offset_hours": family.schedule_offset_hours,
        "guests": float(override.guests),
        "family_away": float(override.away_at(float(target_hour))),
        "wfh_today": float(window.override.work_from_home and day_offset == 0),
        "solar_capacity_kwp": window.effective_kwp,
        "temp_forecast_c": float(window.temperature_c[target])
        + _temperature_forecast_error(seed, target_day, target_hour, horizon_hours),
        "clear_sky_pv_kw": float(window.clear_sky_pv_kw[target]),
        "recent_clearness": recent,
        "lag_1h_consumption_kw": float(window.consumption_kw[now_index - 1]),
        "lag_1h_generation_kw": float(window.generation_kw[now_index - 1]),
        "lag_2h_consumption_kw": float(window.consumption_kw[now_index - 2]),
        "lag_2h_generation_kw": float(window.generation_kw[now_index - 2]),
        "lag_day_consumption_kw": float(window.consumption_kw[lag_day]),
        "lag_day_generation_kw": float(window.generation_kw[lag_day]),
    }
