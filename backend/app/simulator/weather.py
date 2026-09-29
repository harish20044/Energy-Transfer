"""One Chennai date's weather: sky, temperature and rooftop PV output, slot by
slot. Every household on the feeder reads the same `DayWeather` — they share
one sky — and only their installed capacity scales it.

Stochastic, but reproducible from (date, scenario, seed):

- **Daily sky** (Aguiar, Collares-Pereira & Conde, 1988, in spirit): a
  two-state rain/dry Markov chain, since rain persists across consecutive
  days, with each month's rain frequency matching IMD's rainy-day normals;
  a daily clearness index drawn so each month's mean matches NASA POWER's
  all-sky/clear-sky ratio for Chennai.
- **Intra-day clouds** (Aguiar & Collares-Pereira, 1992, "TAG"): a
  first-order autoregressive perturbation around the day's clearness, whose
  spread is largest for broken cloud and vanishes for clear or fully
  overcast skies, then renormalised so the day's total is exactly what the
  daily draw asked for.
- **Temperature** (Parton & Logan, 1981): sine rise from sunrise to a
  mid-afternoon maximum, exponential decay through the night, around a daily
  max/min set by IMD's 1991-2020 normals for the date — nudged warmer on
  clear days and cooler on rainy ones, with those nudges centred so the
  month's average still lands on the normal.
"""

from __future__ import annotations

import calendar
import hashlib
import math
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from app.simulator.climate import (
    DAYS_IN_MONTH,
    MONTHLY_CLEARSKY_GHI_KWH_M2_DAY,
    MONTHLY_MEAN_MAX_C,
    MONTHLY_MEAN_MIN_C,
    clear_sky_index,
    rain_probability,
)
from app.simulator.scenarios import Scenario, override_for
from app.simulator.solar import (
    FloatArray,
    cos_zenith,
    haurwitz_clear_sky_ghi,
    plane_of_array_w_m2,
    pv_output_kw_per_kwp,
    sunrise_sunset_ist,
)

MINUTES_PER_DAY = 24 * 60
# Irradiance and temperature are evaluated at several instants inside each
# slot and averaged, so a slot straddling sunrise gets a partial value
# rather than all-or-nothing.
_SUBSAMPLES_PER_SLOT = 5

# Mean clearness of a rainy day; its draw is uniform over this range.
_RAINY_CLEARNESS_RANGE = (0.22, 0.55)
_RAINY_CLEARNESS_MEAN = sum(_RAINY_CLEARNESS_RANGE) / 2
# How strongly a wet day follows a wet day: a rainy day raises tomorrow's
# chance by this fraction of the remaining headroom. The dry-to-wet
# probability is then solved so the month's long-run frequency is unchanged.
_RAIN_PERSISTENCE = 0.35
_DRY_CLEARNESS_CONCENTRATION = 14.0
# deg C of daily maximum per unit of clearness above the month's mean, and
# the extra cooling of a rainy day.
_TMAX_PER_CLEARNESS_C = 4.0
_TMAX_RAIN_COOLING_C = 1.2
_TMIN_RAIN_COOLING_C = 0.6
# Parton & Logan (1981) coefficients: lag of the maximum after solar noon
# (h), nocturnal decay rate, and lag of the minimum after sunrise (h).
_PL_MAX_LAG_H = 1.86
_PL_NIGHT_DECAY = 2.2
_PL_MIN_LAG_H = -0.17
# Autocorrelation of the cloud perturbation between consecutive 15-minute
# slots, and its spread as a function of the day's clearness K: sigma =
# this * K * (1 - K) — zero for a perfectly clear or fully overcast day,
# largest for broken cloud.
_CLOUD_AR1_PER_15_MIN = 0.8
_CLOUD_SPREAD = 0.6


@dataclass(frozen=True, slots=True)
class DailySky:
    rainy: bool
    clearness: float
    t_max_noise_c: float
    t_min_noise_c: float


@dataclass(frozen=True, slots=True, eq=False)
class DayWeather:
    day: date
    scenario: Scenario
    rainy: bool
    clearness: float
    t_max_c: float
    t_min_c: float
    sunrise_h: float
    sunset_h: float
    # One value per slot, each the mean over that slot.
    temperature_c: FloatArray
    ghi_w_m2: FloatArray
    pv_kw_per_kwp: FloatArray


def _rng(seed: int, *labels: object) -> np.random.Generator:
    digest = hashlib.sha256(":".join(str(x) for x in (seed, *labels)).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


_MONTH_STARTS = tuple(sum(DAYS_IN_MONTH[:m]) for m in range(12))
_MONTH_MIDPOINTS = tuple(
    start + days / 2.0 + 0.5 for start, days in zip(_MONTH_STARTS, DAYS_IN_MONTH, strict=True)
)


def monthly_interp(values: tuple[float, ...], day: date) -> float:
    """A monthly value smoothly interpolated to this date between month
    midpoints, wrapping December into January — so there's no artificial
    jump in climate at midnight on the 1st."""
    doy = float(day.timetuple().tm_yday)
    xs = [_MONTH_MIDPOINTS[-1] - 365.0, *_MONTH_MIDPOINTS, _MONTH_MIDPOINTS[0] + 365.0]
    ys = [values[-1], *values, values[0]]
    return float(np.interp(doy, xs, ys))


def _clear_sky_index_for(day: date) -> float:
    return monthly_interp(tuple(clear_sky_index(m) for m in range(1, 13)), day)


def _rain_probability_for(day: date) -> float:
    return monthly_interp(tuple(rain_probability(m) for m in range(1, 13)), day)


@lru_cache(maxsize=16)
def year_skies(year: int, seed: int) -> tuple[DailySky, ...]:
    """Every day of `year`'s sky, generated in order so rain can persist from
    one day into the next."""
    rng = _rng(seed, "weather-year", year)
    n_days = 366 if calendar.isleap(year) else 365
    skies: list[DailySky] = []
    first = date(year, 1, 1)
    rainy_prev = bool(rng.random() < _rain_probability_for(first))

    for offset in range(n_days):
        day = first + timedelta(days=offset)
        p = _rain_probability_for(day)
        p_wet_after_wet = p + _RAIN_PERSISTENCE * (1.0 - p)
        p_wet_after_dry = p * (1.0 - p_wet_after_wet) / (1.0 - p)
        rainy = bool(rng.random() < (p_wet_after_wet if rainy_prev else p_wet_after_dry))

        if rainy:
            clearness = float(rng.uniform(*_RAINY_CLEARNESS_RANGE))
        else:
            k_mean = _clear_sky_index_for(day)
            dry_mean = min(0.97, max(0.35, (k_mean - p * _RAINY_CLEARNESS_MEAN) / (1.0 - p)))
            kappa = _DRY_CLEARNESS_CONCENTRATION
            clearness = float(
                np.clip(rng.beta(dry_mean * kappa, (1.0 - dry_mean) * kappa), 0.3, 0.99)
            )

        skies.append(
            DailySky(
                rainy=rainy,
                clearness=clearness,
                t_max_noise_c=float(rng.normal(0.0, 0.8)),
                t_min_noise_c=float(rng.normal(0.0, 0.5)),
            )
        )
        rainy_prev = rainy
    return tuple(skies)


def _parton_logan(
    hours: FloatArray, t_max: float, t_min: float, sunrise: float, sunset: float
) -> FloatArray:
    day_len = sunset - sunrise
    night_len = 24.0 - day_len
    start = sunrise + _PL_MIN_LAG_H
    period = day_len + 2.0 * _PL_MAX_LAG_H

    daytime = t_min + (t_max - t_min) * np.sin(np.pi * (hours - start) / period)
    t_at_sunset = t_min + (t_max - t_min) * math.sin(math.pi * (sunset - start) / period)
    since_sunset = np.where(hours >= sunset, hours - sunset, hours + 24.0 - sunset)
    decay = math.exp(-_PL_NIGHT_DECAY)
    night = (
        t_min
        - t_at_sunset * decay
        + (t_at_sunset - t_min) * np.exp(-_PL_NIGHT_DECAY * since_sunset / night_len)
    ) / (1.0 - decay)
    result: FloatArray = np.where((hours >= start) & (hours < sunset), daytime, night)
    return result


@lru_cache(maxsize=512)
def day_weather(day: date, scenario: Scenario, seed: int, tick_minutes: int = 15) -> DayWeather:
    """The complete weather for one date under one scenario."""
    slots = MINUTES_PER_DAY // tick_minutes
    override = override_for(scenario)

    if override is None:
        sky = year_skies(day.year, seed)[day.timetuple().tm_yday - 1]
        rainy, clearness = sky.rainy, sky.clearness
        t_max_noise, t_min_noise = sky.t_max_noise_c, sky.t_min_noise_c
        t_max_shift = t_min_shift = 0.0
    else:
        rng = _rng(seed, "weather-override", day.isoformat(), scenario.value)
        rainy = override.rainy
        clearness = float(np.clip(override.clearness + rng.normal(0.0, 0.02), 0.2, 0.99))
        t_max_noise = float(rng.normal(0.0, 0.5))
        t_min_noise = float(rng.normal(0.0, 0.3))
        t_max_shift, t_min_shift = override.t_max_shift_c, override.t_min_shift_c

    k_mean = _clear_sky_index_for(day)
    p_rain = _rain_probability_for(day)
    t_max = (
        monthly_interp(MONTHLY_MEAN_MAX_C, day)
        + _TMAX_PER_CLEARNESS_C * (clearness - k_mean)
        - _TMAX_RAIN_COOLING_C * (float(rainy) - p_rain)
        + t_max_noise
        + t_max_shift
    )
    t_min = (
        monthly_interp(MONTHLY_MEAN_MIN_C, day)
        - _TMIN_RAIN_COOLING_C * (float(rainy) - p_rain)
        + t_min_noise
        + t_min_shift
    )
    t_max = max(t_max, t_min + 2.0)

    step_h = tick_minutes / 60.0 / _SUBSAMPLES_PER_SLOT
    hours: FloatArray = (np.arange(slots * _SUBSAMPLES_PER_SLOT, dtype=np.float64) + 0.5) * step_h
    cz = cos_zenith(day, hours)
    clear_sky = haurwitz_clear_sky_ghi(cz)
    target_clear_wh = monthly_interp(MONTHLY_CLEARSKY_GHI_KWH_M2_DAY, day) * 1000.0
    modelled_clear_wh = float(clear_sky.sum()) * step_h
    if modelled_clear_wh > 0:
        clear_sky = clear_sky * (target_clear_wh / modelled_clear_wh)

    cloud_rng = _rng(seed, "clouds", day.isoformat(), scenario.value)
    phi = _CLOUD_AR1_PER_15_MIN ** (tick_minutes / 15.0)
    shocks = cloud_rng.normal(0.0, 1.0, slots)
    perturbation = np.empty(slots)
    perturbation[0] = shocks[0]
    for i in range(1, slots):
        perturbation[i] = phi * perturbation[i - 1] + math.sqrt(1.0 - phi**2) * shocks[i]
    sigma = _CLOUD_SPREAD * clearness * (1.0 - clearness)
    slot_clearness = np.clip(clearness + sigma * perturbation, 0.05, 1.05)
    ghi = np.repeat(slot_clearness, _SUBSAMPLES_PER_SLOT) * clear_sky
    total = float(ghi.sum())
    if total > 0:
        ghi = np.minimum(ghi * (clearness * float(clear_sky.sum()) / total), 1.05 * clear_sky)

    sunrise, sunset = sunrise_sunset_ist(day)
    temperature = _parton_logan(hours, t_max, t_min, sunrise, sunset)
    pv = pv_output_kw_per_kwp(plane_of_array_w_m2(day, hours, ghi, cz), temperature)

    def slot_mean(values: FloatArray) -> FloatArray:
        result: FloatArray = values.reshape(slots, _SUBSAMPLES_PER_SLOT).mean(axis=1)
        result.flags.writeable = False
        return result

    return DayWeather(
        day=day,
        scenario=scenario,
        rainy=rainy,
        clearness=clearness,
        t_max_c=t_max,
        t_min_c=t_min,
        sunrise_h=sunrise,
        sunset_h=sunset,
        temperature_c=slot_mean(temperature),
        ghi_w_m2=slot_mean(ghi),
        pv_kw_per_kwp=slot_mean(pv),
    )
