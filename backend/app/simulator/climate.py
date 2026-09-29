"""Chennai's climate: the published numbers every synthetic weather day is
calibrated against, and later cross-checked against by
`app.simulator.validation`.

Every value here is a published observation, not a tuning knob — changing one
changes what "realistic" means for the whole simulation, so each carries its
source. Monthly tables run January to December.
"""

from __future__ import annotations

# Chennai (Nungambakkam), where every household on this feeder sits.
LATITUDE_DEG = 13.0827
LONGITUDE_DEG = 80.2707
# India Standard Time is UTC+5:30, referenced to the 82.5 deg E meridian.
# Chennai sits ~2.2 deg west of it, so local solar noon falls ~9 minutes
# after 12:00 IST (before the equation-of-time correction).
IST_STANDARD_MERIDIAN_DEG = 82.5

# fmt: off
# IMD climatological normals 1991-2020, Chennai (Nungambakkam): mean daily
# maximum and minimum temperature per month, deg C. Source: India
# Meteorological Department, via the station climate table.
MONTHLY_MEAN_MAX_C: tuple[float, ...] = (
    29.3, 30.9, 32.9, 34.5, 37.1, 37.0, 35.3, 34.7, 34.2, 32.1, 29.9, 28.9
)
MONTHLY_MEAN_MIN_C: tuple[float, ...] = (
    21.2, 22.2, 24.2, 26.6, 28.0, 27.5, 26.4, 25.9, 25.6, 24.6, 23.1, 21.9
)

# IMD-cited mean number of rainy days (>= 2.5 mm) per month, Chennai — about
# 60 a year, nearly half of them in the October-December northeast monsoon.
MONTHLY_RAINY_DAYS: tuple[float, ...] = (
    1.4, 0.6, 0.2, 1.0, 1.8, 4.5, 6.7, 8.8, 7.4, 10.6, 11.5, 5.7
)

# NASA POWER climatology 2001-2020 at 13.08 N, 80.27 E (RE community):
# all-sky and clear-sky global horizontal irradiance, kWh/m^2/day. Their
# ratio is how much of a clear sky's sunlight actually reaches the ground in
# an average day of that month — the single number the daily cloud model is
# calibrated to reproduce.
MONTHLY_ALLSKY_GHI_KWH_M2_DAY: tuple[float, ...] = (
    4.98, 5.84, 6.35, 6.50, 5.92, 5.23, 4.87, 4.93, 5.06, 4.63, 4.24, 4.18
)
MONTHLY_CLEARSKY_GHI_KWH_M2_DAY: tuple[float, ...] = (
    5.55, 6.27, 6.79, 7.03, 6.81, 6.77, 6.78, 6.79, 6.64, 6.18, 5.61, 5.22
)

# PVGIS 5.3 (PVGIS-ERA5 2005-2023), 1 kWp crystalline-silicon, 13 deg tilt
# facing south, 14% system losses: daily energy per kWp per month and the
# annual total. The target the PV model is cross-checked against; it agrees
# with installer telemetry for coastal Tamil Nadu (1,400-1,500 kWh/kWp/yr).
PVGIS_MONTHLY_KWH_PER_KWP_DAY: tuple[float, ...] = (
    4.40, 4.90, 4.95, 4.77, 4.42, 3.76, 3.44, 3.63, 3.89, 3.85, 3.46, 3.70
)
PVGIS_ANNUAL_KWH_PER_KWP = 1494.0

DAYS_IN_MONTH: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
# fmt: on


def clear_sky_index(month: int) -> float:
    """Average fraction of clear-sky irradiance reaching the ground in this
    month (1-based), from NASA POWER's all-sky / clear-sky ratio."""
    return MONTHLY_ALLSKY_GHI_KWH_M2_DAY[month - 1] / MONTHLY_CLEARSKY_GHI_KWH_M2_DAY[month - 1]


def rain_probability(month: int) -> float:
    """Chance a given day of this month (1-based) is a rainy day."""
    return MONTHLY_RAINY_DAYS[month - 1] / DAYS_IN_MONTH[month - 1]
