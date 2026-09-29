"""One household's electricity use for one day, appliance by appliance.

A bottom-up, occupancy-driven model in the style of CREST (Richardson,
Thomson, Infield & Clifford, 2010, "Domestic electricity use: a
high-resolution energy demand model"): a household draws power because a
specific person is home, awake or asleep in a specific room, doing a
specific thing — not because a smooth curve says so. Each appliance below
switches on from the family's routine (`app.simulator.family`) and the day's
weather (`app.simulator.weather`):

- **Cooling**: one 1.5-ton inverter split AC per bedroom, switched on as a
  room's occupants fall asleep with a probability rising steeply with the
  temperature (Prayas eMARC: likely above ~28 deg C), run through the sleep
  or until a timer; afternoon sessions for whoever is home in the heat.
  Power follows outdoor temperature, as an inverter compressor's does.
- **Fans, lights**: every occupied room; lights only once it's genuinely
  dark (by irradiance — an overcast afternoon needs them too).
- **Fridge**: always on, working harder on hot days (Prayas: 461 kWh/yr).
- **Water**: the morning sump-to-tank motor pump, an RO purifier topping up
  its tank (25-60 W), a geyser only on genuinely cool mornings.
- **Kitchen** (cooking itself is mostly LPG): mixer-grinder, the evening
  wet grinder for idli/dosa batter, electric kettle, induction cooktop,
  rice cooker, microwave, chimney — each only where the family owns one.
- **Laundry**: washing machine, iron box.
- **Entertainment & work**: hall TV, a grandparents' bedroom TV, laptops on
  WFH days, a teenager's gaming PC, phones charging.
- **EV charging**: an electric scooter on a 700 W home charger (Ather),
  occasionally an electric car on a 3.3 kW wall box — Tamil Nadu's 2025 EV
  registrations are over 80% two-wheelers.
- **Standby**: router, set-top box, the solar inverter's own draw, and a
  mosquito-repellent vaporiser (5-7 W) in every occupied bedroom all night.

Deterministic given (household, date, scenario, override, seed).
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from app.simulator.family import (
    BEDROOMS,
    HOME_DURING_DAY,
    NO_OVERRIDE,
    WORKING,
    Family,
    HouseholdOverride,
    Occupation,
    Role,
    Status,
    generate_family,
    member_days,
    status_at,
    with_guests,
)
from app.simulator.scenarios import Scenario
from app.simulator.solar import FloatArray
from app.simulator.weather import MINUTES_PER_DAY, DayWeather, day_weather

# --- Air conditioning --------------------------------------------------------
# A 1.5-ton 5-star inverter split draws ~0.95-1.2 kW in measured Indian use;
# modelled as a part-load floor rising with outdoor temperature to full
# compressor speed, which it also runs at for the first half hour of pulling
# a warm room down to setpoint.
AC_MIN_KW = 0.55
AC_MAX_KW = 1.45
_AC_TEMP_LOW_C = 24.0
_AC_TEMP_HIGH_C = 38.0
_AC_PULL_DOWN_H = 0.5
# Temperature as a room's occupants fall asleep at which half of households
# switch the AC on, and how sharply that rises either side (logistic width).
_SLEEP_AC_MIDPOINT_C = 27.0
_SLEEP_AC_WIDTH_C = 0.9
# A sleep this warm keeps the AC on until it ends, rather than until a timer.
_HOT_SLEEP_MEAN_C = 28.5
_DAY_AC_MIDPOINT_C = 34.0
_ELDERLY_HEAT_SENSITIVITY_C = 1.0

CEILING_FAN_KW = 0.06
_LED_HALL_KW = 0.03
_LED_KITCHEN_KW = 0.015
_LED_PER_AWAKE_PERSON_KW = 0.012
_OUTDOOR_LIGHT_KW = 0.018
_DARK_GHI_W_M2 = 80.0  # below this horizontal irradiance a room needs its lights

_FRIDGE_KW_AT_25C = 0.052
_FRIDGE_TEMP_COEFFICIENT = 0.025
# Router, set-top box and TV standby, chargers idling, and the hybrid solar
# inverter's own consumption (~20 W for a home unit).
_STANDBY_KW = 0.055
_MOSQUITO_VAPORISER_KW = 0.006
_PERSONAL_DEVICES_KW = 0.01

_PUMP_KW = 0.75  # 1 HP monoblock, sump to overhead tank
_RO_PURIFIER_KW = 0.05
_GEYSER_KW = 2.0
_GEYSER_BATH_H = 0.2
_GEYSER_NEEDED_BELOW_C = 23.5

_MIXER_KW = 0.55
_WET_GRINDER_KW = 0.2
_KETTLE_KW = 1.5
_INDUCTION_KW = 1.2  # a 1.8-2 kW hob on ~60-70% of full power
_RICE_COOKER_KW = 0.7
_RICE_COOKER_WARM_KW = 0.05
_MICROWAVE_KW = 1.2
_CHIMNEY_KW = 0.15

_WASHER_KWH_PER_CYCLE = 0.45
_WASHER_CYCLE_H = 70 / 60
_WASHER_CYCLES_PER_PERSON_WEEK = 0.8
_IRON_KW = 0.4  # 1 kW element on ~40% duty under its thermostat

_TV_KW = 0.09
_BEDROOM_TV_KW = 0.07
_LAPTOP_KW = 0.07
_STUDY_LAPTOP_KW = 0.04
_GAMING_PC_KW = 0.15

_EV_SCOOTER_KW = 0.7  # Ather 700 W home charger
_EV_CAR_KW = 3.3  # Tata Nexon EV 3.3 kW wall box

_LOAD_NOISE_SIGMA = 0.05

CATEGORIES: tuple[str, ...] = (
    "cooling",
    "fans",
    "lighting",
    "kitchen",
    "refrigerator",
    "water",
    "laundry",
    "entertainment",
    "ev",
    "standby",
)


@dataclass(frozen=True, slots=True, eq=False)
class HouseholdDay:
    household_id: str
    day: date
    family: Family
    weather: DayWeather
    statuses: npt.NDArray[np.int8]  # (members, slots) of family.Status values
    room_ac_kw: FloatArray  # (BEDROOMS, slots)
    breakdown: dict[str, FloatArray]  # category -> kW per slot
    consumption_kw: FloatArray
    generation_kw: FloatArray


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class _Timeline:
    """Slot arithmetic for one day: turn "on from 06:40 for 25 minutes"
    into the average power it contributes to each slot."""

    def __init__(self, tick_minutes: int) -> None:
        self.slots = MINUTES_PER_DAY // tick_minutes
        self.step_h = tick_minutes / 60.0
        self.starts: FloatArray = np.arange(self.slots, dtype=np.float64) * self.step_h
        self.midpoints: FloatArray = self.starts + self.step_h / 2.0

    def fraction(self, start_h: float, duration_h: float) -> FloatArray:
        """Fraction of each slot covered by [start, start+duration), wrapping
        past midnight onto the early-morning slots."""
        start_h %= 24.0
        end_h = start_h + max(0.0, duration_h)
        covered = np.zeros(self.slots)
        for lo, hi in ((start_h, min(end_h, 24.0)), (0.0, max(0.0, end_h - 24.0))):
            if hi > lo:
                covered += np.clip(
                    np.minimum(hi, self.starts + self.step_h) - np.maximum(lo, self.starts),
                    0.0,
                    None,
                )
        result: FloatArray = np.clip(covered / self.step_h, 0.0, 1.0)
        return result

    def slot_of(self, hour: float) -> int:
        return min(self.slots - 1, int((hour % 24.0) / self.step_h))

    def blocks(self, mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
        """Contiguous runs of True as (start slot, length), treating the day
        as circular so a sleep that spans midnight is one block."""
        n = self.slots
        if mask.all():
            return [(0, n)]
        if not mask.any():
            return []
        start = int(np.argmin(mask))  # begin scanning at a False slot
        runs: list[tuple[int, int]] = []
        run_start, length = -1, 0
        for k in range(1, n + 1):
            i = (start + k) % n
            if mask[i]:
                if length == 0:
                    run_start = i
                length += 1
            elif length:
                runs.append((run_start, length))
                length = 0
        if length:
            runs.append((run_start, length))
        return runs


def _ac_power_kw(temperature_c: FloatArray) -> FloatArray:
    span = (temperature_c - _AC_TEMP_LOW_C) / (_AC_TEMP_HIGH_C - _AC_TEMP_LOW_C)
    result: FloatArray = AC_MIN_KW + (AC_MAX_KW - AC_MIN_KW) * np.clip(span, 0.0, 1.0)
    return result


def _rng_for(household_id: str, seed: int, label: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{household_id}:{label}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))  # noqa: S311 -- deterministic synthetic data


def _cooling(
    family: Family,
    statuses: npt.NDArray[np.int8],
    weather: DayWeather,
    timeline: _Timeline,
    rng: random.Random,
    weekend: bool,
) -> FloatArray:
    """(BEDROOMS, slots) of AC power."""
    temps = weather.temperature_c
    on = np.zeros((BEDROOMS, timeline.slots))
    pull = np.zeros((BEDROOMS, timeline.slots))
    offset_c = family.habits.ac_comfort_offset_c

    def session(room: int, start: float, duration: float) -> None:
        on[room - 1] = np.maximum(on[room - 1], timeline.fraction(start, duration))
        pull[room - 1] = np.maximum(
            pull[room - 1], timeline.fraction(start, min(duration, _AC_PULL_DOWN_H))
        )

    # Sleep: one decision per block of someone asleep in the room — a night,
    # or a night-shift worker's morning — from the temperature as it starts.
    for room in range(1, BEDROOMS + 1):
        sleepers = [i for i, m in enumerate(family.members) if m.sleeping_room == room]
        if not sleepers:
            continue
        asleep = (statuses[sleepers] == Status.ASLEEP).any(axis=0)
        elderly = any(family.members[i].role is Role.GRANDPARENT for i in sleepers)
        midpoint = _SLEEP_AC_MIDPOINT_C + offset_c - (_ELDERLY_HEAT_SENSITIVITY_C if elderly else 0)
        for start_slot, length in timeline.blocks(asleep):
            start_h = float(timeline.starts[start_slot])
            block_h = length * timeline.step_h
            if rng.random() >= _logistic((float(temps[start_slot]) - midpoint) / _SLEEP_AC_WIDTH_C):
                continue
            block_slots = [(start_slot + k) % timeline.slots for k in range(length)]
            hot = float(temps[block_slots].mean()) >= _HOT_SLEEP_MEAN_C
            duration = block_h if hot else min(block_h, rng.uniform(4.5, 7.0))  # the sleep timer
            precool = rng.uniform(0.25, 0.5)
            session(room, start_h - precool, duration + precool)

    # Afternoon: whoever is actually home and awake through the heat of the day.
    two_pm = timeline.slot_of(14.0)
    for i, member in enumerate(family.members):
        own_room = member.sleeping_room
        if own_room is None or statuses[i, two_pm] != Status.HOME:
            continue
        if member.occupation in (Occupation.INFANT, Occupation.PRESCHOOL, Occupation.SCHOOL):
            continue  # with a caregiver, whose own session covers them
        if member.occupation in WORKING and not weekend:
            start, duration = rng.uniform(11.5, 13.0), rng.uniform(3.0, 5.0)  # working from home
        elif member.occupation in HOME_DURING_DAY:
            start, duration = rng.uniform(12.75, 14.0), rng.uniform(1.5, 3.0)
        elif weekend:
            start, duration = rng.uniform(13.5, 14.5), rng.uniform(1.0, 2.0)
        else:
            continue
        elderly = member.role is Role.GRANDPARENT
        midpoint = _DAY_AC_MIDPOINT_C + offset_c - (_ELDERLY_HEAT_SENSITIVITY_C if elderly else 0)
        if rng.random() < _logistic((float(temps[timeline.slot_of(start)]) - midpoint) / 1.0):
            session(own_room, start, duration)

    power = _ac_power_kw(temps)
    result: FloatArray = on * power + pull * (AC_MAX_KW - power)
    return result


@lru_cache(maxsize=1024)
def simulate_household_day(
    household_id: str,
    member_count: int,
    solar_capacity_kwp: float,
    day: date,
    scenario: Scenario,
    seed: int,
    tick_minutes: int = 15,
    override: HouseholdOverride = NO_OVERRIDE,
) -> HouseholdDay:
    family = with_guests(generate_family(household_id, member_count, seed), override.guests)
    habits = family.habits
    weather = day_weather(day, scenario, seed, tick_minutes)
    timeline = _Timeline(tick_minutes)
    rng = _rng_for(household_id, seed, f"appliances:{day.isoformat()}:{scenario.value}:{override}")
    weekend = day.weekday() >= 5
    offset = family.schedule_offset_hours
    temps = weather.temperature_c
    members = len(family.members)
    caregiver_home = family.count(*HOME_DURING_DAY) > 0

    days = member_days(family, day, seed, override)
    statuses = np.array(
        [[status_at(d, float(t)) for t in timeline.midpoints] for d in days], dtype=np.int8
    )
    awake_home = (statuses == Status.HOME).sum(axis=0).astype(np.float64)
    anyone_home = awake_home > 0
    anyone_in = (statuses != Status.AWAY).any(axis=0)

    def block(start: float, duration: float, kw: float) -> FloatArray:
        result: FloatArray = timeline.fraction(start, duration) * kw
        return result

    def while_home(values: FloatArray) -> FloatArray:
        result: FloatArray = np.where(anyone_home, values, 0.0)
        return result

    zeros = np.zeros(timeline.slots)
    cat: dict[str, FloatArray] = {name: zeros.copy() for name in CATEGORIES}

    # Cooling.
    room_ac = _cooling(family, statuses, weather, timeline, rng, weekend)
    cat["cooling"] = room_ac.sum(axis=0)

    # Fans: the hall while anyone's up, each bedroom while someone sleeps in
    # it (on low alongside the AC — common Indian practice); vaporisers too.
    hall_fans = np.where(
        temps > 27.0, 2 * CEILING_FAN_KW, np.where(temps > 23.0, CEILING_FAN_KW, 0)
    )
    cat["fans"] = while_home(hall_fans)
    for room in range(1, BEDROOMS + 1):
        sleepers = np.zeros(timeline.slots, dtype=bool)
        for i, member in enumerate(family.members):
            if member.sleeping_room == room:
                sleepers |= statuses[i] == Status.ASLEEP
        ac_running = room_ac[room - 1] > 0.5 * AC_MIN_KW
        fan = np.where(ac_running, CEILING_FAN_KW / 2, np.where(temps > 22.0, CEILING_FAN_KW, 0.0))
        cat["fans"] = cat["fans"] + np.where(sleepers, fan, 0.0)
        if habits.mosquito_vaporiser:
            cat["standby"] = cat["standby"] + np.where(sleepers, _MOSQUITO_VAPORISER_KW, 0.0)

    # Lighting: occupied rooms once it's dark, plus the gate/balcony light.
    dark = weather.ghi_w_m2 < _DARK_GHI_W_M2
    indoor = _LED_HALL_KW + _LED_KITCHEN_KW + _LED_PER_AWAKE_PERSON_KW * awake_home
    cat["lighting"] = np.where(dark & anyone_home, indoor, 0.0)
    outdoor_off = 30.0 if rng.random() < 0.3 else rng.uniform(22.5, 23.5)  # 30 = until dawn
    cat["lighting"] = cat["lighting"] + block(
        weather.sunset_h,
        min(outdoor_off, 24.0 + weather.sunrise_h) - weather.sunset_h,
        _OUTDOOR_LIGHT_KW,
    )

    cat["refrigerator"] = _FRIDGE_KW_AT_25C * (1.0 + _FRIDGE_TEMP_COEFFICIENT * (temps - 25.0))
    cat["standby"] = cat["standby"] + _STANDBY_KW

    # Water.
    water = block(
        rng.uniform(5.75, 7.0) + offset,
        (15 + 6 * members) / 60.0 * rng.uniform(0.8, 1.2),
        _PUMP_KW,
    )
    if rng.random() < 0.3:
        water += block(rng.uniform(17.5, 19.0), 0.25, _PUMP_KW)
    if habits.ro_purifier:
        # Refills its tank after the morning, midday and evening draws.
        for start, minutes in ((6.5, 40), (12.25, 20), (19.25, 40)):
            water += block(
                start + rng.uniform(0.0, 0.5), minutes / 60 * (members / 4), _RO_PURIFIER_KW
            )
    if not habits.solar_water_heater:
        p_bath = min(0.6, max(0.0, (_GEYSER_NEEDED_BELOW_C - weather.t_min_c) / 3.0))
        for member, member_day in zip(family.members, days, strict=True):
            if member.age >= 3 and rng.random() < p_bath:
                water += block(
                    member_day.wake_h + rng.uniform(0.25, 1.0), _GEYSER_BATH_H, _GEYSER_KW
                )
    cat["water"] = np.where(anyone_in, water, 0.0)

    # Kitchen.
    kitchen = zeros.copy()
    breakfast = rng.uniform(6.25, 7.25) + offset
    dinner = rng.uniform(19.0, 20.0) + offset
    if rng.random() < 0.9:
        kitchen += block(breakfast + rng.uniform(0.25, 0.5), rng.uniform(0.17, 0.25), _MIXER_KW)
    if caregiver_home and rng.random() < 0.5:
        kitchen += block(rng.uniform(11.5, 12.25), 0.17, _MIXER_KW)
    if rng.random() < 0.4:
        kitchen += block(dinner, 0.17, _MIXER_KW)
    if rng.random() < habits.wet_grinder_days_per_week / 7.0:
        kitchen += block(rng.uniform(17.0, 19.5), rng.uniform(0.75, 1.0), _WET_GRINDER_KW)
    if habits.electric_kettle:
        kitchen += block(breakfast, 4 / 60, _KETTLE_KW)
        if rng.random() < 0.5:
            kitchen += block(rng.uniform(16.5, 17.5), 4 / 60, _KETTLE_KW)  # evening tea
    if habits.induction_cooktop:
        kitchen += block(breakfast + 0.1, rng.uniform(0.25, 0.4), _INDUCTION_KW)
        if rng.random() < 0.6:
            kitchen += block(dinner + 0.2, rng.uniform(0.25, 0.4), _INDUCTION_KW)
    if habits.electric_rice_cooker:
        cook_start = rng.uniform(6.5, 7.5) + offset
        kitchen += block(cook_start, 25 / 60, _RICE_COOKER_KW)
        kitchen += block(cook_start + 25 / 60, 2.0, _RICE_COOKER_WARM_KW)
    if habits.microwave and rng.random() < 0.5:
        kitchen += block(rng.uniform(19.5, 20.75), 5 / 60, _MICROWAVE_KW)
    if habits.kitchen_chimney:
        kitchen += block(breakfast, 0.75, _CHIMNEY_KW)
        kitchen += block(dinner, 0.75, _CHIMNEY_KW)
    cat["kitchen"] = np.where(anyone_in, kitchen, 0.0)

    # Laundry.
    laundry = zeros.copy()
    if rng.random() < min(1.0, _WASHER_CYCLES_PER_PERSON_WEEK * members / 7.0):
        if caregiver_home:
            start = rng.uniform(8.0, 10.5)
        elif weekend:
            start = rng.uniform(8.5, 11.0)
        else:
            start = rng.uniform(6.0, 7.0) + offset  # set running before leaving
        laundry += block(start, _WASHER_CYCLE_H, _WASHER_KWH_PER_CYCLE / _WASHER_CYCLE_H)
    if habits.irons_at_home and rng.random() < (2 / 7 if weekend else 4 / 7):
        laundry += block(rng.uniform(7.0, 8.0) + offset, rng.uniform(0.33, 0.5), _IRON_KW)
    cat["laundry"] = np.where(anyone_in, laundry, 0.0)

    # Entertainment and work: TVs only while someone's actually up at home.
    tv = zeros.copy()
    if rng.random() < 0.9:
        start = rng.uniform(19.0, 20.0)
        tv = np.maximum(tv, block(start, rng.uniform(21.5, 22.75) + offset - start, 1.0))
    if caregiver_home:
        if rng.random() < 0.6:
            tv = np.maximum(tv, block(10.5, 1.5, 1.0))
        if rng.random() < 0.7:
            tv = np.maximum(tv, block(18.0, 1.0, 1.0))
    if family.count(Occupation.SCHOOL, Occupation.PRESCHOOL) and rng.random() < 0.5:
        tv = np.maximum(tv, block(16.5, 1.5, 1.0))
    if weekend and rng.random() < 0.6:
        tv = np.maximum(tv, block(10.0, 3.0, 1.0))
    entertainment = while_home(tv * _TV_KW)
    for i, member in enumerate(family.members):
        home = statuses[i] == Status.HOME
        if member.occupation in WORKING and not weekend and not days[i].away:
            entertainment = entertainment + np.where(home, block(9.5, 8.5, _LAPTOP_KW), 0.0)
        if member.occupation in (Occupation.COLLEGE, Occupation.SCHOOL) and member.age >= 12:
            entertainment = entertainment + np.where(home, block(18.5, 3.0, _STUDY_LAPTOP_KW), 0.0)
        if habits.gaming_pc and member.age >= 13 and member.role is Role.CHILD:
            evening = block(rng.uniform(19.5, 20.5), rng.uniform(1.0, 2.5), _GAMING_PC_KW)
            if weekend:
                evening = evening + block(
                    rng.uniform(14.0, 15.0), rng.uniform(1.0, 2.0), _GAMING_PC_KW
                )
            entertainment = entertainment + np.where(home, evening, 0.0)
        if (
            habits.bedroom_tv
            and member.role is Role.GRANDPARENT
            and member.index
            == min(j for j, m in enumerate(family.members) if m.role is Role.GRANDPARENT)
        ):
            entertainment = entertainment + np.where(home, block(18.0, 3.5, _BEDROOM_TV_KW), 0.0)
    cat["entertainment"] = entertainment + _PERSONAL_DEVICES_KW * awake_home

    # EV charging: plugged in once the rider is back for the evening.
    ev = zeros.copy()
    if habits.ev_scooter:
        daily_kwh = rng.uniform(0.6, 1.4)  # ~20-45 km of city riding
        ev += block(rng.uniform(19.5, 21.5), daily_kwh / _EV_SCOOTER_KW, _EV_SCOOTER_KW)
    if habits.ev_car and rng.random() < 0.5:  # topped up every other day
        top_up_kwh = rng.uniform(5.0, 9.0)
        ev += block(rng.uniform(21.0, 23.0), top_up_kwh / _EV_CAR_KW, _EV_CAR_KW)
    cat["ev"] = np.where(anyone_in, ev, 0.0)

    total = np.sum([cat[name] for name in CATEGORIES], axis=0)
    noise_rng = np.random.default_rng(rng.getrandbits(63))
    noise = np.exp(noise_rng.normal(0.0, _LOAD_NOISE_SIGMA, timeline.slots))
    breakdown = {name: cat[name] * noise for name in CATEGORIES}
    consumption: FloatArray = total * noise

    generation: FloatArray = (
        weather.pv_kw_per_kwp
        * solar_capacity_kwp
        * (1.0 - min(1.0, max(0.0, override.panel_derate)))
    )
    for arr in (consumption, generation, room_ac, *breakdown.values()):
        arr.flags.writeable = False
    statuses.flags.writeable = False

    return HouseholdDay(
        household_id=household_id,
        day=day,
        family=family,
        weather=weather,
        statuses=statuses,
        room_ac_kw=room_ac,
        breakdown=breakdown,
        consumption_kw=consumption,
        generation_kw=generation,
    )
