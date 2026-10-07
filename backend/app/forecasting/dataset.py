"""Training data for the forecaster, generated straight from the simulator —
never from the live database. Reproducible from (households, dates, seed),
the same determinism guarantee the rest of the simulator holds (ADR-0006).

One row per (household, day, hour, sampled horizon). So the model has seen
what users can ask of it before they ask:

- most days follow Chennai's climatology, but a share are "what-if"
  weather (heatwave, monsoon rain, broken cloud, clear);
- a share of household-days carry a family what-if: guests staying, the
  family out for a few hours, a work-from-home day, or dusty panels;
- each forecast origin gets four horizons, one from each lead-time band
  (1-3 h, 4-8 h, 9-15 h, 16-24 h), covering every horizon a session can
  ask for at a quarter of the rows of using all 24.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from app.forecasting.features import (
    HOURS_PER_DAY,
    TODAY_OFFSET,
    feature_row,
    features_for_household,
    hourly_window,
    target_index,
)
from app.simulator.family import NO_OVERRIDE, HouseholdOverride
from app.simulator.scenarios import Scenario

_WHAT_IF_WEATHER_SHARE = 0.2
_WHAT_IF_WEATHERS = (Scenario.CLEAR, Scenario.CLOUDY, Scenario.RAINY, Scenario.HEATWAVE)
_FAMILY_WHAT_IF_SHARE = 0.15
_HORIZON_BANDS: tuple[tuple[int, int], ...] = ((1, 3), (4, 8), (9, 15), (16, 24))


@dataclass(frozen=True, slots=True)
class HouseholdConfig:
    household_id: str
    member_count: int
    solar_capacity_kwp: float


def _rng(seed: int, *labels: object) -> random.Random:
    return random.Random(":".join(str(x) for x in (seed, *labels)))  # noqa: S311 -- synthetic data


def scenario_for_day(day: date, seed: int) -> Scenario:
    rng = _rng(seed, "train-scenario", day.isoformat())
    if rng.random() < _WHAT_IF_WEATHER_SHARE:
        return rng.choice(_WHAT_IF_WEATHERS)
    return Scenario.AUTO


def override_for(household_id: str, day: date, seed: int) -> HouseholdOverride:
    rng = _rng(seed, "train-override", household_id, day.isoformat())
    if rng.random() >= _FAMILY_WHAT_IF_SHARE:
        return NO_OVERRIDE
    guests = 2 if rng.random() < 0.4 else 0
    away_from = away_to = None
    if rng.random() < 0.4:
        away_from = round(rng.uniform(8.0, 20.0) * 4) / 4
        away_to = away_from + round(rng.uniform(2.0, 8.0) * 4) / 4
    return HouseholdOverride(
        guests=guests,
        away_from=away_from,
        away_to=away_to,
        work_from_home=rng.random() < 0.3,
        panel_derate=round(rng.uniform(0.1, 0.4), 2) if rng.random() < 0.3 else 0.0,
    )


def generate_training_rows(
    configs: tuple[HouseholdConfig, ...],
    *,
    start: date,
    num_days: int,
    seed: int,
    history_hours: int = 0,
) -> list[dict[str, float]]:
    """`history_hours` > 0 adds the household's metered load and solar for
    that many hours before each forecast origin (`hist_consumption_1` is
    the hour just before it), for sequence models; the LightGBM features
    never read them."""
    if not 0 <= history_hours <= TODAY_OFFSET:
        msg = f"history_hours must be 0-{TODAY_OFFSET}, got {history_hours}"
        raise ValueError(msg)
    rows: list[dict[str, float]] = []
    for offset in range(num_days):
        day = start + timedelta(days=offset)
        scenario = scenario_for_day(day, seed)
        for config in configs:
            override = override_for(config.household_id, day, seed)
            window = hourly_window(
                config.household_id,
                config.member_count,
                config.solar_capacity_kwp,
                day,
                scenario,
                seed,
                override=override,
            )
            family = features_for_household(config.household_id, config.member_count, seed)
            horizon_rng = _rng(seed, "horizons", config.household_id, day.isoformat())
            for hour in range(HOURS_PER_DAY):
                now_index = TODAY_OFFSET + hour
                for lo, hi in _HORIZON_BANDS:
                    horizon = horizon_rng.randint(lo, hi)
                    row = feature_row(
                        window,
                        now_index=now_index,
                        horizon_hours=horizon,
                        family=family,
                        seed=seed,
                    )
                    target = target_index(now_index, horizon)
                    row["consumption_kw"] = float(window.consumption_kw[target])
                    row["generation_kw"] = float(window.generation_kw[target])
                    row["day_of_year"] = float(day.timetuple().tm_yday)
                    for back in range(1, history_hours + 1):
                        row[f"hist_consumption_{back}"] = float(
                            window.consumption_kw[now_index - back]
                        )
                        row[f"hist_generation_{back}"] = float(
                            window.generation_kw[now_index - back]
                        )
                    rows.append(row)
    return rows
