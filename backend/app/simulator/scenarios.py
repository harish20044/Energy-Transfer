"""The weather a simulated day runs under.

`AUTO` is the realistic default: the day's sky and temperature are drawn
from Chennai's own climatology for the chosen date — a May afternoon is hot
and clear, a November day has a real chance of northeast-monsoon rain. The
others are "what if" overrides for that same date: force a clear sky, broken
cloud, a monsoon downpour, or an IMD-defined heatwave, and watch how the
same households and the same market respond.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Scenario(StrEnum):
    AUTO = "auto"
    CLEAR = "clear"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    HEATWAVE = "heatwave"


@dataclass(frozen=True, slots=True)
class WeatherOverride:
    rainy: bool
    # Fraction of the date's clear-sky irradiance that reaches the ground.
    clearness: float
    t_max_shift_c: float = 0.0
    t_min_shift_c: float = 0.0


_OVERRIDES: dict[Scenario, WeatherOverride] = {
    Scenario.CLEAR: WeatherOverride(rainy=False, clearness=0.97),
    # Broken cumulus: the most *variable* sky, not just a dimmer one — the
    # intra-day cloud model gives mid-range clearness its largest swings.
    Scenario.CLOUDY: WeatherOverride(rainy=False, clearness=0.55),
    Scenario.RAINY: WeatherOverride(rainy=True, clearness=0.30),
    # IMD's heatwave criterion for a coastal station: a maximum of at least
    # 37 deg C and at least 4.5 deg C above normal. Nights stay warm too,
    # which is what actually drives Chennai's AC load.
    Scenario.HEATWAVE: WeatherOverride(
        rainy=False, clearness=0.93, t_max_shift_c=4.5, t_min_shift_c=2.0
    ),
}


def override_for(scenario: Scenario) -> WeatherOverride | None:
    """None for AUTO — the day's weather comes from climatology instead."""
    return _OVERRIDES.get(scenario)
