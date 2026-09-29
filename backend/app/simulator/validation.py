"""Cross-checks the synthetic data against published real-world measurements.

    docker exec energy-backend python -m app.simulator.validation [--json out.json]

Every check pairs a number the simulator produces with a range from a named
source. A failing check means the simulation has drifted from Chennai
reality, not that a test is flaky: the synthetic data is deterministic from
its seed. `tests/validation` runs this same suite in CI.

Weather and solar are judged over many synthetic years (a single year is one
random draw of rain and cloud, and would be judged unfairly against a
multi-decade climatology); household consumption over one full calendar year
for all ten seeded households.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.simulator import climate
from app.simulator.household import AC_MIN_KW, CATEGORIES, simulate_household_day
from app.simulator.scenarios import Scenario
from app.simulator.solar import sunrise_sunset_ist
from app.simulator.weather import day_weather

_SRC_IMD = (
    "IMD climatological normals 1991-2020, Chennai (Nungambakkam)",
    "https://mausam.imd.gov.in/chennai/mcdata/extreme_chennai.pdf",
)
_SRC_NASA = (
    "NASA POWER climatology 2001-2020, 13.08N 80.27E",
    "https://power.larc.nasa.gov/",
)
_SRC_PVGIS = (
    "PVGIS 5.3 (ERA5 2005-2023), 1 kWp, 13 deg tilt, 14% loss",
    "https://re.jrc.ec.europa.eu/pvg_tools/en/",
)
_SRC_SUN = ("sunrise-sunset.org, Chennai 2026", "https://sunrise-sunset.org/in/chennai")
_SRC_PRAYAS = (
    "Prayas (Energy Group) eMARC smart-meter study, 115 households",
    "https://energy.prayaspune.org/our-work/article-and-blog/electricity-load-patterns",
)
_SRC_PRAYAS_FRIDGE = (
    "Prayas eMARC: refrigerators average 461 kWh/year",
    "https://energy.prayaspune.org/our-work/article-and-blog/refrigerator-electricity-consumption-patterns",
)
_SRC_CHENNAI_AC = (
    "Chennai AC usage: 6-10 h/day, March-November (CoolingInsights city guide)",
    "https://coolinginsights.com/city-guide/chennai",
)
_SRC_CHENNAI_BILLS = (
    "Chennai 3BHK with AC: 500-700 units/month (Surya's Solar, 2026)",
    "https://www.suryassolar.com/blog/2026-04-27-why-is-electricity-bill-high-in-summer-tamil-nadu",
)

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    group: str
    title: str
    measured: float
    low: float
    high: float
    unit: str
    source: str
    url: str
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.low <= self.measured <= self.high


@dataclass(slots=True)
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    # Month-by-month and hour-by-hour series behind the checks, for charts.
    series: dict[str, list[float]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_json(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [{**asdict(c), "passed": c.passed} for c in self.checks],
            "series": self.series,
        }


def _weather_checks(report: ValidationReport, seed: int, years: range) -> None:
    months: list[int] = []
    pv, ghi, t_max, t_min, rainy = [], [], [], [], []
    for year in years:
        first = date(year, 1, 1)
        for offset in range(365):
            day = first + timedelta(days=offset)
            w = day_weather(day, Scenario.AUTO, seed)
            step_h = 24.0 / len(w.pv_kw_per_kwp)
            months.append(day.month)
            pv.append(float(w.pv_kw_per_kwp.sum()) * step_h)
            ghi.append(float(w.ghi_w_m2.sum()) * step_h / 1000.0)
            t_max.append(w.t_max_c)
            t_min.append(w.t_min_c)
            rainy.append(float(w.rainy))

    m = np.array(months)
    pv_a, ghi_a = np.array(pv), np.array(ghi)
    t_max_a, t_min_a, rain_a = np.array(t_max), np.array(t_min), np.array(rainy)
    n_years = len(years)

    def by_month(values: np.ndarray, reducer: str = "mean") -> list[float]:
        out = []
        for i in range(1, 13):
            sel = values[m == i]
            out.append(float(sel.sum() / n_years) if reducer == "per_year" else float(sel.mean()))
        return out

    pv_month, ghi_month = by_month(pv_a), by_month(ghi_a)
    tmax_month, tmin_month = by_month(t_max_a), by_month(t_min_a)
    rain_month = by_month(rain_a, "per_year")
    report.series.update(
        {
            "pv_kwh_per_kwp_day": pv_month,
            "pv_pvgis": list(climate.PVGIS_MONTHLY_KWH_PER_KWP_DAY),
            "ghi_kwh_m2_day": ghi_month,
            "ghi_nasa": list(climate.MONTHLY_ALLSKY_GHI_KWH_M2_DAY),
            "t_max_c": tmax_month,
            "t_max_imd": list(climate.MONTHLY_MEAN_MAX_C),
            "t_min_c": tmin_month,
            "t_min_imd": list(climate.MONTHLY_MEAN_MIN_C),
            "rainy_days": rain_month,
            "rainy_days_imd": list(climate.MONTHLY_RAINY_DAYS),
        }
    )

    annual = float(pv_a.sum() / n_years)
    report.checks.append(
        Check(
            "solar-annual-yield",
            "Solar",
            "Annual PV yield per kWp",
            annual,
            0.95 * climate.PVGIS_ANNUAL_KWH_PER_KWP,
            1.05 * climate.PVGIS_ANNUAL_KWH_PER_KWP,
            "kWh/kWp/yr",
            *_SRC_PVGIS,
            note="PVGIS gives 1,494; coastal Tamil Nadu installer telemetry 1,400-1,500.",
        )
    )
    worst_pv = max(
        abs(sim / ref - 1.0)
        for sim, ref in zip(pv_month, climate.PVGIS_MONTHLY_KWH_PER_KWP_DAY, strict=True)
    )
    report.checks.append(
        Check(
            "solar-monthly-yield",
            "Solar",
            "Worst month's PV yield vs PVGIS",
            100 * worst_pv,
            0.0,
            12.0,
            "% off",
            *_SRC_PVGIS,
            note=(
                "PVGIS uses ERA5 irradiance, the simulator NASA POWER; "
                "they differ by a few % by month."
            ),
        )
    )
    worst_ghi = max(
        abs(sim / ref - 1.0)
        for sim, ref in zip(ghi_month, climate.MONTHLY_ALLSKY_GHI_KWH_M2_DAY, strict=True)
    )
    report.checks.append(
        Check(
            "ghi-monthly",
            "Solar",
            "Worst month's irradiance vs NASA POWER",
            100 * worst_ghi,
            0.0,
            5.0,
            "% off",
            *_SRC_NASA,
        )
    )
    report.checks.append(
        Check(
            "ghi-peak-month",
            "Solar",
            "Sunniest month (1=Jan)",
            float(int(np.argmax(ghi_month)) + 1),
            3.0,
            4.0,
            "month",
            *_SRC_NASA,
            note="NASA POWER: March-April, before the southwest-monsoon haze.",
        )
    )

    night_output = 0.0
    for day in (date(2026, 1, 15), date(2026, 4, 15), date(2026, 7, 15), date(2026, 10, 15)):
        w = day_weather(day, Scenario.CLEAR, seed)
        step_h = 24.0 / len(w.pv_kw_per_kwp)
        for i, value in enumerate(w.pv_kw_per_kwp):
            if (i + 1) * step_h <= w.sunrise_h or i * step_h >= w.sunset_h:
                night_output = max(night_output, float(value))
    report.checks.append(
        Check(
            "solar-zero-at-night",
            "Solar",
            "Max PV output with the sun below the horizon",
            night_output,
            0.0,
            0.0,
            "kW/kWp",
            *_SRC_SUN,
        )
    )

    sun_events = (
        ("Earliest sunrise (31 May)", sunrise_sunset_ist(date(2026, 5, 31))[0], 5 + 40 / 60),
        ("Latest sunrise (23 Jan)", sunrise_sunset_ist(date(2026, 1, 23))[0], 6 + 34 / 60),
        ("Earliest sunset (19 Nov)", sunrise_sunset_ist(date(2026, 11, 19))[1], 17 + 40 / 60),
        ("Latest sunset (9 Jul)", sunrise_sunset_ist(date(2026, 7, 9))[1], 18 + 40 / 60),
    )
    worst_min = max(abs(sim - ref) * 60 for _, sim, ref in sun_events)
    report.checks.append(
        Check(
            "sun-times",
            "Solar",
            "Sunrise/sunset error at the year's extremes",
            worst_min,
            0.0,
            3.0,
            "minutes",
            *_SRC_SUN,
            note="; ".join(
                f"{name}: {_fmt_clock(sim)} vs {_fmt_clock(ref)}" for name, sim, ref in sun_events
            ),
        )
    )
    day_lengths = (
        ("June solstice", date(2026, 6, 21), 12 + 56 / 60),
        ("December solstice", date(2026, 12, 22), 11 + 23 / 60),
    )
    worst_len = max(
        abs((sunrise_sunset_ist(d)[1] - sunrise_sunset_ist(d)[0]) - ref) * 60
        for _, d, ref in day_lengths
    )
    report.checks.append(
        Check(
            "day-length",
            "Solar",
            "Day length error at the solstices",
            worst_len,
            0.0,
            3.0,
            "minutes",
            *_SRC_SUN,
        )
    )

    worst_tmax = max(
        abs(a - b) for a, b in zip(tmax_month, climate.MONTHLY_MEAN_MAX_C, strict=True)
    )
    worst_tmin = max(
        abs(a - b) for a, b in zip(tmin_month, climate.MONTHLY_MEAN_MIN_C, strict=True)
    )
    report.checks.append(
        Check(
            "temp-max",
            "Weather",
            "Worst month's mean daily max vs IMD",
            worst_tmax,
            0.0,
            1.0,
            "deg C",
            *_SRC_IMD,
        )
    )
    report.checks.append(
        Check(
            "temp-min",
            "Weather",
            "Worst month's mean daily min vs IMD",
            worst_tmin,
            0.0,
            1.0,
            "deg C",
            *_SRC_IMD,
        )
    )
    annual_rain = float(rain_a.sum() / n_years)
    imd_rain = sum(climate.MONTHLY_RAINY_DAYS)
    report.checks.append(
        Check(
            "rainy-days",
            "Weather",
            "Rainy days per year",
            annual_rain,
            0.85 * imd_rain,
            1.15 * imd_rain,
            "days",
            *_SRC_IMD,
        )
    )
    ne_share = sum(rain_month[9:12]) / annual_rain if annual_rain else 0.0
    report.checks.append(
        Check(
            "monsoon-share",
            "Weather",
            "Share of rainy days in Oct-Dec (northeast monsoon)",
            100 * ne_share,
            38.0,
            55.0,
            "%",
            *_SRC_IMD,
            note="IMD-cited normals put 27.8 of ~60 rainy days (46%) in Oct-Dec.",
        )
    )


def _fmt_clock(hours: float) -> str:
    h = int(hours)
    return f"{h:02d}:{round((hours - h) * 60):02d}"


def _household_checks(report: ValidationReport, seed: int, year: int) -> None:
    from app.scripts.seed_households import HOUSEHOLDS

    days = [date(year, 1, 1) + timedelta(days=d) for d in range(365)]
    months = np.array([d.month for d in days])
    daily_kwh = np.zeros((len(HOUSEHOLDS), len(days)))
    fridge_kwh = 0.0
    shape = {1: np.zeros(24), 5: np.zeros(24)}
    shape_days = {1: 0, 5: 0}
    ac_hours_by_month = np.zeros(12)
    ac_nights_by_month = np.zeros(12)
    room_nights_by_month = np.zeros(12)
    category_kwh = {name: np.zeros(12) for name in CATEGORIES}

    for hi, h in enumerate(HOUSEHOLDS):
        for di, day in enumerate(days):
            hd = simulate_household_day(
                h.id, h.member_count, h.solar_capacity_kwp, day, Scenario.AUTO, seed
            )
            step_h = 24.0 / len(hd.consumption_kw)
            daily_kwh[hi, di] = float(hd.consumption_kw.sum()) * step_h
            fridge_kwh += float(hd.breakdown["refrigerator"].sum()) * step_h
            for name in CATEGORIES:
                category_kwh[name][day.month - 1] += float(hd.breakdown[name].sum()) * step_h
            if day.month in shape:
                per_hour = len(hd.consumption_kw) // 24
                shape[day.month] += hd.consumption_kw.reshape(24, per_hour).mean(axis=1)
                shape_days[day.month] += 1
            running = hd.room_ac_kw >= 0.5 * AC_MIN_KW
            hours = running.sum(axis=1) * step_h
            occupied_rooms = {
                m.sleeping_room for m in hd.family.members if m.sleeping_room is not None
            }
            room_nights_by_month[day.month - 1] += len(occupied_rooms)
            ac_nights_by_month[day.month - 1] += int((hours > 0).sum())
            ac_hours_by_month[day.month - 1] += float(hours.sum())

    n_hh = len(HOUSEHOLDS)
    units_per_month = daily_kwh.mean(axis=1) * 365 / 12
    monthly_kwh_per_day = [float(daily_kwh[:, months == i].mean()) for i in range(1, 13)]
    report.series.update(
        {
            "consumption_kwh_per_day": monthly_kwh_per_day,
            "ac_hours_per_night": [
                float(ac_hours_by_month[i] / ac_nights_by_month[i])
                if ac_nights_by_month[i]
                else 0.0
                for i in range(12)
            ],
            "ac_share_of_room_nights": [
                float(ac_nights_by_month[i] / room_nights_by_month[i]) for i in range(12)
            ],
            "load_shape_jan_kw": [float(x) for x in shape[1] / shape_days[1]],
            "load_shape_may_kw": [float(x) for x in shape[5] / shape_days[5]],
            "household_units_per_month": [float(x) for x in units_per_month],
            "household_ids": [float(i + 1) for i in range(n_hh)],
            **{
                f"category_{name}_kwh_per_day": [
                    float(category_kwh[name][i] / n_hh / (months == i + 1).sum()) for i in range(12)
                ]
                for name in CATEGORIES
            },
        }
    )

    big = [i for i, h in enumerate(HOUSEHOLDS) if h.member_count >= 4]
    report.checks.append(
        Check(
            "units-per-month",
            "Consumption",
            "Average units/month, families of 4+",
            float(units_per_month[big].mean()),
            500.0,
            750.0,
            "units",
            *_SRC_CHENNAI_BILLS,
            note="Benchmark is a 3BHK with AC; these homes have one bedroom more.",
        )
    )
    ratio = monthly_kwh_per_day[4] / monthly_kwh_per_day[0]
    report.checks.append(
        Check(
            "summer-winter-ratio",
            "Consumption",
            "May vs January consumption",
            ratio,
            1.8,
            4.0,
            "x",
            *_SRC_PRAYAS,
            note=(
                "Bracketed from both sides: above the 1.3x Prayas measured in far milder Pune, "
                "below the 4-5x rupee jump Chennai bills show (progressive slabs make the "
                "rupee ratio exceed the units ratio)."
            ),
        )
    )
    peak_hours = [ac_hours_by_month[i] / ac_nights_by_month[i] for i in (3, 4, 5)]
    report.checks.append(
        Check(
            "ac-hours",
            "Consumption",
            "AC hours per night in use, Apr-Jun",
            float(np.mean(peak_hours)),
            6.0,
            10.0,
            "h",
            *_SRC_CHENNAI_AC,
        )
    )
    winter_share = (ac_nights_by_month[0] + ac_nights_by_month[11]) / (
        room_nights_by_month[0] + room_nights_by_month[11]
    )
    summer_share = sum(ac_nights_by_month[i] for i in (3, 4, 5)) / sum(
        room_nights_by_month[i] for i in (3, 4, 5)
    )
    report.checks.append(
        Check(
            "ac-season-winter",
            "Consumption",
            "Bedrooms using AC on Dec-Jan nights",
            100 * winter_share,
            0.0,
            20.0,
            "%",
            *_SRC_CHENNAI_AC,
            note="Chennai's AC season runs March-November.",
        )
    )
    report.checks.append(
        Check(
            "ac-season-summer",
            "Consumption",
            "Bedrooms using AC on Apr-Jun nights",
            100 * summer_share,
            60.0,
            100.0,
            "%",
            *_SRC_CHENNAI_AC,
        )
    )
    report.checks.append(
        Check(
            "fridge",
            "Consumption",
            "Refrigerator energy per year",
            fridge_kwh / n_hh,
            400.0,
            600.0,
            "kWh",
            *_SRC_PRAYAS_FRIDGE,
            note="461 kWh measured in cooler Pune; compressor work rises with Chennai's heat.",
        )
    )
    may = shape[5] / shape_days[5]
    may_peak = int(np.argmax(may))
    report.checks.append(
        Check(
            "summer-peak-hour",
            "Consumption",
            "Hour of peak load in May (0-23; 24+ = after midnight)",
            float(may_peak if may_peak >= 12 else may_peak + 24),
            22.0,
            26.0,
            "h",
            *_SRC_PRAYAS,
            note="eMARC: May load peaks around midnight-1 am in AC homes.",
        )
    )
    jan = shape[1] / shape_days[1]
    report.checks.append(
        Check(
            "winter-morning-peak",
            "Consumption",
            "Hour of January's morning peak",
            float(int(np.argmax(jan[4:12])) + 4),
            6.0,
            9.0,
            "h",
            *_SRC_PRAYAS,
            note="eMARC: a morning peak around 7-9 am in winter.",
        )
    )
    report.checks.append(
        Check(
            "winter-night-base",
            "Consumption",
            "January night load, 1-4 am",
            float(jan[1:4].mean()) * 1000,
            100.0,
            400.0,
            "W",
            *_SRC_PRAYAS,
            note=(
                "eMARC: 100-150 W in (smaller) Pune homes; "
                "these add bedroom fans and a bigger fridge."
            ),
        )
    )


def run_validation(
    *, seed: int = 42, weather_years: range = range(2001, 2021), household_year: int = 2026
) -> ValidationReport:
    report = ValidationReport()
    report.series["months"] = [float(i) for i in range(1, 13)]
    _weather_checks(report, seed, weather_years)
    _household_checks(report, seed, household_year)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="also write the full report to this path")
    args = parser.parse_args()

    report = run_validation()
    width = max(len(c.title) for c in report.checks)
    for check in report.checks:
        mark = "PASS" if check.passed else "FAIL"
        print(  # noqa: T201
            f"[{mark}] {check.title:<{width}}  {check.measured:9.2f} {check.unit:<10} "
            f"expected {check.low:g}-{check.high:g}   ({check.source})"
        )
    passed = sum(c.passed for c in report.checks)
    print(f"\n{passed}/{len(report.checks)} checks passed")  # noqa: T201
    if args.json:
        Path(args.json).write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
