"""Objective O1: the forecaster on days it never saw.

Regenerates exactly the held-out test days of `app.forecasting.train` (day
of year % 5 == 0 in the training year — each day's rows are reproducible on
their own, so only those days are generated), and scores the saved LightGBM
models, raw and conformally calibrated, against the seasonal-naive baseline
with `score_quantiles` — the same scorer the LSTM benchmark
(`app.evaluation.lstm`) uses, whose saved result is folded in when present.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pandas as pd

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.model import (
    ARTIFACTS_DIR,
    load_conformal,
    load_models,
    predict_batch,
    score_quantiles,
    seasonal_naive_predictions,
)
from app.forecasting.train import NUM_DAYS, SEED, SPLIT_MODULUS, TRAINING_YEAR_START
from app.scripts.seed_households import HOUSEHOLDS

LSTM_RESULT_FILE = ARTIFACTS_DIR / "lstm_benchmark.json"
NMAE_TARGET = 0.25  # at least 25% below seasonal-naive
CALIBRATION_TOLERANCE = 0.03  # P10 within 7-13% below, P90 within 87-93%


def held_out_frame(*, history_hours: int = 0, max_days: int | None = None) -> pd.DataFrame:
    configs = tuple(HouseholdConfig(h.id, h.member_count, h.solar_capacity_kwp) for h in HOUSEHOLDS)
    rows: list[dict[str, float]] = []
    days = 0
    for offset in range(NUM_DAYS):
        day = TRAINING_YEAR_START + timedelta(days=offset)
        if day.timetuple().tm_yday % SPLIT_MODULUS != 0:
            continue
        if max_days is not None and days >= max_days:
            break
        days += 1
        rows.extend(
            generate_training_rows(
                configs, start=day, num_days=1, seed=SEED, history_hours=history_hours
            )
        )
    return pd.DataFrame(rows)


def evaluate_forecaster(*, max_days: int | None = None) -> dict[str, Any]:
    """`max_days` limits the test days scored (for quick checks only)."""
    df = held_out_frame(max_days=max_days)
    models = load_models()
    if not models:
        msg = "no trained forecaster in app/forecasting/artifacts — run app.forecasting.train"
        raise RuntimeError(msg)
    scores = {
        "lightgbm_calibrated": score_quantiles(df, predict_batch(models, df, load_conformal())),
        "lightgbm_raw": score_quantiles(df, predict_batch(models, df)),
        "seasonal_naive": score_quantiles(df, seasonal_naive_predictions(df)),
    }
    lstm = json.loads(LSTM_RESULT_FILE.read_text()) if LSTM_RESULT_FILE.exists() else None
    if lstm is not None:
        scores["lstm_calibrated"] = lstm["scores"]["lstm_calibrated"]
        scores["lstm_raw"] = lstm["scores"]["lstm_raw"]

    model, naive = scores["lightgbm_calibrated"], scores["seasonal_naive"]
    targets: dict[str, Any] = {}
    for target in model:
        improvement = 1.0 - model[target]["nmae_p50"] / naive[target]["nmae_p50"]
        calibrated = (
            abs(model[target]["below_p10"] - 0.10) <= CALIBRATION_TOLERANCE
            and abs(model[target]["below_p90"] - 0.90) <= CALIBRATION_TOLERANCE
        )
        targets[target] = {
            "nmae_improvement": improvement,
            "pinball_skill": 1.0 - model[target]["pinball"] / naive[target]["pinball"],
            "calibrated": calibrated,
            "met": improvement >= NMAE_TARGET and calibrated,
        }
    return {
        "test_rows": len(df),
        "test_days": int(df["day_of_year"].nunique()),
        "scores": scores,
        "targets": targets,
        "lstm": None if lstm is None else {k: v for k, v in lstm.items() if k != "scores"},
        "met": all(t["met"] for t in targets.values()),
    }
