"""Synthetic training data for the forecaster, generated straight from the
pure simulator (`app.simulator.profiles`) — never from the live database.
Every row is reproducible from (household configs, day count, seed): run
this twice with the same seed and get byte-identical training data, the same
determinism guarantee the rest of the domain layer holds itself to
(ADR-0006).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.forecasting.features import HORIZONS_HOURS, HourlyLags, feature_row, household_family
from app.simulator.profiles import consumption_kw, generation_kw
from app.simulator.scenarios import Scenario

TICKS_PER_HOUR = 4
HOURS_PER_DAY = 24
TICK_MINUTES = 15

# Real Indian weather is clear far more often than it storms — roughly this
# split across a year for most of the country per IMD climatological
# normals: a large majority of days see full sun, a substantial minority are
# overcast or monsoon-affected, and genuine heatwave-intensity days are a
# small fraction even across the hottest months.
_SCENARIO_WEIGHTS: dict[Scenario, float] = {
    Scenario.CLEAR: 0.55,
    Scenario.CLOUDY: 0.35,
    Scenario.HEATWAVE: 0.10,
}


@dataclass(frozen=True, slots=True)
class HouseholdConfig:
    household_id: str
    member_count: int
    solar_capacity_kwp: float


def _hourly_series(
    config: HouseholdConfig, *, num_days: int, seed: int, rng: random.Random
) -> list[tuple[float, float]]:
    """This household's own (consumption_kw, generation_kw) at hourly
    resolution across `num_days` synthetic days — one independent scenario
    draw per day, since a real day's weather doesn't change hour to hour."""
    day_scenarios = [
        rng.choices(list(_SCENARIO_WEIGHTS), weights=list(_SCENARIO_WEIGHTS.values()), k=1)[0]
        for _ in range(num_days)
    ]

    series: list[tuple[float, float]] = []
    for hour_index in range(num_days * HOURS_PER_DAY):
        scenario = day_scenarios[hour_index // HOURS_PER_DAY]
        base_tick = hour_index * TICKS_PER_HOUR
        cons_total = 0.0
        gen_total = 0.0
        for sub in range(TICKS_PER_HOUR):
            tick_index = base_tick + sub
            cons_total += consumption_kw(
                config.household_id,
                tick_index,
                member_count=config.member_count,
                tick_minutes=TICK_MINUTES,
                scenario=scenario,
                seed=seed,
            )
            gen_total += generation_kw(
                tick_index,
                solar_capacity_kwp=config.solar_capacity_kwp,
                tick_minutes=TICK_MINUTES,
                scenario=scenario,
            )
        series.append((cons_total / TICKS_PER_HOUR, gen_total / TICKS_PER_HOUR))
    return series


def generate_training_rows(
    configs: tuple[HouseholdConfig, ...], *, num_days: int, seed: int
) -> list[dict[str, float]]:
    """One row per (household, hour, forecast horizon): features built only
    from calendar/routine facts and past readings, target the actual future
    reading. `seed` drives both the simulator's own noise and which scenario
    each household draws on each synthetic day, so a training run is fully
    reproducible from it."""
    rng = random.Random(seed)  # noqa: S311 -- reproducible synthetic data, not a secret
    rows: list[dict[str, float]] = []
    max_horizon = max(HORIZONS_HOURS)

    for config in configs:
        family = household_family(config.household_id, config.member_count, seed)
        series = _hourly_series(config, num_days=num_days, seed=seed, rng=rng)
        total_hours = len(series)

        # Need a full day of history for the 24h lag, and room ahead for the
        # largest horizon.
        for now_hour in range(HOURS_PER_DAY, total_hours - max_horizon):
            lag_1h = series[now_hour - 1]
            lag_2h = series[now_hour - 2]
            lag_24h = series[now_hour - 24]
            lags = HourlyLags(
                lag_1h_consumption_kw=lag_1h[0],
                lag_1h_generation_kw=lag_1h[1],
                lag_2h_consumption_kw=lag_2h[0],
                lag_2h_generation_kw=lag_2h[1],
                lag_24h_consumption_kw=lag_24h[0],
                lag_24h_generation_kw=lag_24h[1],
            )
            for horizon in HORIZONS_HOURS:
                target_hour = now_hour + horizon
                target_cons, target_gen = series[target_hour]
                row = feature_row(
                    family=family,
                    solar_capacity_kwp=config.solar_capacity_kwp,
                    target_hour_of_day=float(target_hour % HOURS_PER_DAY),
                    target_is_weekend=(target_hour // HOURS_PER_DAY) % 7 in (5, 6),
                    horizon_hours=horizon,
                    lags=lags,
                )
                row["consumption_kw"] = target_cons
                row["generation_kw"] = target_gen
                rows.append(row)

    return rows
