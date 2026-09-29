"""Solar geometry and rooftop PV output for Chennai — physics, not a curve fit.

The chain, each step a standard, citable model:

1. Sun position from the date and IST clock time: Spencer (1971) declination
   and equation of time, so sunrise, sunset and solar noon move through the
   year exactly as they do in Chennai.
2. Clear-sky global horizontal irradiance: Haurwitz (1945), rescaled so each
   clear day's total matches NASA POWER's clear-sky climatology for the date.
3. Beam/diffuse split: Erbs, Klein & Duffie (1982) correlation on the
   instantaneous clearness index.
4. Irradiance on a 13 deg south-tilted panel (latitude tilt, the standard
   Indian rooftop install): isotropic-sky transposition (Liu & Jordan, 1963).
5. Cell temperature from the NOCT model and a -0.37 %/deg C power
   coefficient — Chennai's heat genuinely costs output — then fixed system
   losses (inverter, wiring, soiling, mismatch).

Validated against PVGIS 5.3 in `app.simulator.validation`.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import numpy.typing as npt

from app.simulator.climate import IST_STANDARD_MERIDIAN_DEG, LATITUDE_DEG, LONGITUDE_DEG

FloatArray = npt.NDArray[np.float64]

SOLAR_CONSTANT_W_M2 = 1367.0
PANEL_TILT_DEG = 13.0
GROUND_ALBEDO = 0.2
NOCT_C = 45.0
POWER_TEMP_COEFFICIENT_PER_C = -0.0037
# Inverter (~97%), DC/AC wiring (~2%), soiling (~5% — Chennai's dust between
# cleanings), module mismatch and ageing (~3%): the non-thermal losses left
# once cell temperature is modelled explicitly. Calibrated so the annual
# yield lands on PVGIS's 1,494 kWh/kWp for this site (see validation).
SYSTEM_EFFICIENCY = 0.856
# Standard refraction-corrected horizon for sunrise/sunset.
_HORIZON_DEG = -0.833
# Beam transposition blows up as the sun grazes the horizon; below this
# elevation the (tiny) beam component is treated as diffuse instead.
_MIN_COS_ZENITH_FOR_BEAM = 0.087


def _day_angle(day: date) -> float:
    return 2.0 * math.pi * (day.timetuple().tm_yday - 1) / 365.0


def declination_rad(day: date) -> float:
    """Spencer (1971)."""
    b = _day_angle(day)
    return (
        0.006918
        - 0.399912 * math.cos(b)
        + 0.070257 * math.sin(b)
        - 0.006758 * math.cos(2 * b)
        + 0.000907 * math.sin(2 * b)
        - 0.002697 * math.cos(3 * b)
        + 0.00148 * math.sin(3 * b)
    )


def equation_of_time_min(day: date) -> float:
    """Spencer (1971), minutes."""
    b = _day_angle(day)
    return 229.18 * (
        0.000075
        + 0.001868 * math.cos(b)
        - 0.032077 * math.sin(b)
        - 0.014615 * math.cos(2 * b)
        - 0.04089 * math.sin(2 * b)
    )


def _solar_time_offset_h(day: date) -> float:
    """Hours to add to IST clock time to get local apparent solar time."""
    return (4.0 * (LONGITUDE_DEG - IST_STANDARD_MERIDIAN_DEG) + equation_of_time_min(day)) / 60.0


def sunrise_sunset_ist(day: date) -> tuple[float, float]:
    """Refraction-corrected sunrise and sunset in IST decimal hours."""
    phi = math.radians(LATITUDE_DEG)
    delta = declination_rad(day)
    cos_ws = (math.sin(math.radians(_HORIZON_DEG)) - math.sin(phi) * math.sin(delta)) / (
        math.cos(phi) * math.cos(delta)
    )
    ws_h = math.degrees(math.acos(max(-1.0, min(1.0, cos_ws)))) / 15.0
    offset = _solar_time_offset_h(day)
    return 12.0 - ws_h - offset, 12.0 + ws_h - offset


def cos_zenith(day: date, clock_hours: FloatArray) -> FloatArray:
    """Cosine of the solar zenith angle at each IST clock time."""
    phi = math.radians(LATITUDE_DEG)
    delta = declination_rad(day)
    solar_time = clock_hours + _solar_time_offset_h(day)
    omega = np.radians(15.0 * (solar_time - 12.0))
    result: FloatArray = math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * np.cos(
        omega
    )
    return result


def _cos_incidence_on_panel(day: date, clock_hours: FloatArray) -> FloatArray:
    """Angle of incidence on a south-facing panel tilted PANEL_TILT_DEG
    (Duffie & Beckman eq. 1.6.7, northern hemisphere)."""
    phi_minus_beta = math.radians(LATITUDE_DEG - PANEL_TILT_DEG)
    delta = declination_rad(day)
    solar_time = clock_hours + _solar_time_offset_h(day)
    omega = np.radians(15.0 * (solar_time - 12.0))
    result: FloatArray = math.sin(delta) * math.sin(phi_minus_beta) + math.cos(delta) * math.cos(
        phi_minus_beta
    ) * np.cos(omega)
    return result


def extraterrestrial_normal_w_m2(day: date) -> float:
    return SOLAR_CONSTANT_W_M2 * (
        1.0 + 0.033 * math.cos(2.0 * math.pi * day.timetuple().tm_yday / 365.0)
    )


def haurwitz_clear_sky_ghi(cos_z: FloatArray) -> FloatArray:
    """Haurwitz (1945) clear-sky GHI, W/m^2; zero with the sun below the horizon."""
    safe = np.clip(cos_z, 1e-6, None)
    ghi = 1098.0 * safe * np.exp(-0.057 / safe)
    result: FloatArray = np.where(cos_z > 0.0, ghi, 0.0)
    return result


def _erbs_diffuse_fraction(kt: FloatArray) -> FloatArray:
    """Erbs, Klein & Duffie (1982)."""
    mid = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    result: FloatArray = np.where(kt <= 0.22, 1.0 - 0.09 * kt, np.where(kt <= 0.80, mid, 0.165))
    return result


def plane_of_array_w_m2(
    day: date, clock_hours: FloatArray, ghi: FloatArray, cos_z: FloatArray
) -> FloatArray:
    """Irradiance on the tilted panel from horizontal GHI (isotropic sky)."""
    g0h = extraterrestrial_normal_w_m2(day) * np.clip(cos_z, 0.0, None)
    kt = np.where(g0h > 1.0, np.clip(ghi / np.where(g0h > 1.0, g0h, 1.0), 0.0, 1.0), 0.0)
    diffuse = ghi * _erbs_diffuse_fraction(kt)
    beam_h = ghi - diffuse

    cos_theta = np.clip(_cos_incidence_on_panel(day, clock_hours), 0.0, None)
    beam_ok = cos_z > _MIN_COS_ZENITH_FOR_BEAM
    ratio = np.where(beam_ok, cos_theta / np.where(beam_ok, cos_z, 1.0), 0.0)
    beam_tilted = np.where(beam_ok, beam_h * ratio, 0.0)
    diffuse_all = np.where(beam_ok, diffuse, diffuse + beam_h)

    tilt = math.radians(PANEL_TILT_DEG)
    poa: FloatArray = (
        beam_tilted
        + diffuse_all * (1.0 + math.cos(tilt)) / 2.0
        + ghi * GROUND_ALBEDO * (1.0 - math.cos(tilt)) / 2.0
    )
    return poa


def pv_output_kw_per_kwp(poa_w_m2: FloatArray, ambient_c: FloatArray) -> FloatArray:
    """AC output per kWp of installed panels, capped at nameplate (the
    inverter is sized to the array)."""
    cell_c = ambient_c + (NOCT_C - 20.0) / 800.0 * poa_w_m2
    temp_factor = 1.0 + POWER_TEMP_COEFFICIENT_PER_C * (cell_c - 25.0)
    result: FloatArray = np.clip(poa_w_m2 / 1000.0 * temp_factor * SYSTEM_EFFICIENCY, 0.0, 1.0)
    return result
