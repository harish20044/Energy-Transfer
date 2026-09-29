"""Train the forecaster, calibrate it, evaluate it on unseen days, and write
its artifacts.

    docker exec energy-backend python -m app.forecasting.train

Offline only: a full synthetic year for all ten households straight from the
simulator (no database, no network). Days are split three ways — never rows,
so no hour of a calibration or test day ever informs training:

- day-of-year % 5 == 0 -> **test** (never touched until the final report)
- day-of-year % 5 == 1 -> **calibration** (conformal offsets only)
- everything else      -> **fit** (the six LightGBM models)

The model files, conformal offsets and the evaluation report (metrics.json)
land in app/forecasting/artifacts/ and are committed, so a fresh checkout
serves calibrated forecasts without training on first request.
"""

from __future__ import annotations

import json
import time
from datetime import date

import pandas as pd

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.model import (
    ARTIFACTS_DIR,
    evaluate,
    fit_conformal_offsets,
    save_conformal,
    train_models,
)
from app.scripts.seed_households import HOUSEHOLDS

TRAINING_YEAR_START = date(2025, 1, 1)
NUM_DAYS = 365
SEED = 42
_SPLIT_MODULUS = 5


def _print_report(title: str, report: dict[str, dict[str, float]]) -> None:
    print(title)  # noqa: T201
    for target, m in report.items():
        print(  # noqa: T201
            f"  {target:>15}: pinball {m['pinball_model']:.4f} vs seasonal-naive "
            f"{m['pinball_seasonal_naive']:.4f} -> skill {m['skill_vs_naive']:+.1%}, "
            f"P10-P90 coverage {m['p10_p90_coverage']:.1%} (nominal 80%)"
        )


def main() -> None:
    configs = tuple(HouseholdConfig(h.id, h.member_count, h.solar_capacity_kwp) for h in HOUSEHOLDS)

    start = time.monotonic()
    df = pd.DataFrame(
        generate_training_rows(configs, start=TRAINING_YEAR_START, num_days=NUM_DAYS, seed=SEED)
    )
    print(f"Generated {len(df):,} rows in {time.monotonic() - start:.1f}s")  # noqa: T201

    split = df["day_of_year"].astype(int) % _SPLIT_MODULUS
    fit_df, calibration_df, test_df = df[split >= 2], df[split == 1], df[split == 0]

    start = time.monotonic()
    models = train_models(fit_df)
    print(f"Trained 6 models on {len(fit_df):,} rows in {time.monotonic() - start:.1f}s")  # noqa: T201

    offsets = fit_conformal_offsets(models, calibration_df)
    save_conformal(offsets)

    raw = evaluate(models, test_df)
    calibrated = evaluate(models, test_df, offsets)
    _print_report(f"\nTest days, raw quantiles ({len(test_df):,} rows):", raw)
    _print_report("Test days, conformally calibrated:", calibrated)

    (ARTIFACTS_DIR / "metrics.json").write_text(
        json.dumps(
            {
                "data": f"{NUM_DAYS} synthetic days from {TRAINING_YEAR_START}, "
                f"{len(configs)} households, seed {SEED}",
                "rows": {
                    "fit": len(fit_df),
                    "calibration": len(calibration_df),
                    "test": len(test_df),
                },
                "conformal_offsets_kw": offsets,
                "test_raw": raw,
                "test_calibrated": calibrated,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
