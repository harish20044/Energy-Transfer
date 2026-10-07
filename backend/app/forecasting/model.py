"""Tier 2 of the forecasting ladder (ADR-0004): LightGBM quantile regression
as the production forecaster, with conformal calibration.

Two targets (consumption, generation) x three quantiles (P10/P50/P90) = six
independently trained boosters — the standard way to do gradient-boosted
quantile regression, since each quantile is its own pinball-loss objective.

Two corrections on top of raw LightGBM output, both from the literature:

- **Quantile crossing** (P10 predicted above P50 for some row, an artefact
  of independent quantile models) is fixed by sorting the three predictions
  (Chernozhukov, Fernandez-Val & Galichon, 2010).
- **Miscalibration**: quantile regressors fitted on finite data tend to be
  overconfident — their P10-P90 band holds fewer than 80% of outcomes.
  Conformalized quantile regression (Romano, Patterson & Candes, 2019)
  widens the band by an amount measured on calibration days the models
  never trained on, which restores the nominal coverage with a
  finite-sample guarantee. Offsets are kept per target and per horizon,
  since uncertainty grows the further ahead you look.

Evaluated the way probabilistic load forecasts are in the literature (Hong &
Fan, 2016; Gneiting & Raftery, 2007): pinball loss, skill against the
seasonal-naive baseline, and interval coverage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd

from app.forecasting.features import FEATURE_COLUMNS, TARGET_CONSUMPTION, TARGET_GENERATION

Quantile = Literal["p10", "p50", "p90"]
QUANTILES: dict[Quantile, float] = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
TARGETS = (TARGET_CONSUMPTION, TARGET_GENERATION)
# Nominal miscoverage of the P10-P90 band.
_ALPHA = 0.2

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
_CONFORMAL_FILE = "conformal.json"

ModelMap = dict[tuple[str, Quantile], lgb.Booster]
QuantilePredictions = dict[str, dict[Quantile, npt.NDArray[np.float64]]]
# target -> horizon (hours) -> (kW to lower P10 by, kW to raise P90 by).
ConformalOffsets = dict[str, dict[int, tuple[float, float]]]

_PARAMS = {
    "objective": "quantile",
    "metric": "quantile",
    "num_leaves": 31,
    "min_data_in_leaf": 50,
    "learning_rate": 0.06,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "seed": 42,
    "deterministic": True,
    "verbose": -1,
}
_BOOST_ROUNDS = 300
# Generation rows count as daylight (and so get calibrated/scored) above this
# clear-sky potential; at night both forecast and actual are exactly zero.
_DAYLIGHT_CLEAR_SKY_KW = 0.05


def _model_path(target: str, quantile: Quantile, artifacts_dir: Path) -> Path:
    return artifacts_dir / f"{target}_{quantile}.txt"


def train_models(
    df: pd.DataFrame, *, artifacts_dir: Path = ARTIFACTS_DIR, boost_rounds: int = _BOOST_ROUNDS
) -> ModelMap:
    """Train and save all six quantile models."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    models: ModelMap = {}
    features = df[list(FEATURE_COLUMNS)]
    for target in TARGETS:
        for quantile, alpha in QUANTILES.items():
            booster = lgb.train(
                {**_PARAMS, "alpha": alpha},
                lgb.Dataset(features, label=df[target]),
                num_boost_round=boost_rounds,
            )
            booster.save_model(str(_model_path(target, quantile, artifacts_dir)))
            models[(target, quantile)] = booster
    return models


def load_models(*, artifacts_dir: Path = ARTIFACTS_DIR) -> ModelMap:
    """All six trained boosters, or an empty dict if any artifact is missing
    — callers treat that as "fall back to the seasonal-naive baseline"."""
    models: ModelMap = {}
    for target in TARGETS:
        for quantile in QUANTILES:
            path = _model_path(target, quantile, artifacts_dir)
            if not path.exists():
                return {}
            models[(target, quantile)] = lgb.Booster(model_file=str(path))
    return models


def _daylight(features: pd.DataFrame) -> npt.NDArray[np.bool_]:
    return np.asarray(features["clear_sky_pv_kw"].to_numpy() > _DAYLIGHT_CLEAR_SKY_KW)


def predict_batch(
    models: ModelMap, features: pd.DataFrame, conformal: ConformalOffsets | None = None
) -> QuantilePredictions:
    """P10/P50/P90 for both targets for every row: sorted into a
    non-crossing order, widened by the conformal offsets if given, and
    clamped at zero (negative power isn't physical)."""
    matrix = features[list(FEATURE_COLUMNS)]
    raw = {
        target: np.column_stack(
            [np.asarray(models[(target, q)].predict(matrix), dtype=np.float64) for q in QUANTILES]
        )
        for target in TARGETS
    }
    return finish_quantiles(raw, features, conformal)


def finish_quantiles(
    raw: dict[str, npt.NDArray[np.float64]],
    features: pd.DataFrame,
    conformal: ConformalOffsets | None = None,
) -> QuantilePredictions:
    """Any forecaster's raw (rows x [P10, P50, P90]) output per target, made
    usable: sorted so quantiles never cross (Chernozhukov et al., 2010),
    widened by conformal offsets if given, and clamped at zero."""
    horizons = features["horizon_hours"].to_numpy().astype(int)
    daylight = _daylight(features)
    result: QuantilePredictions = {}
    for target in TARGETS:
        ordered = np.sort(raw[target], axis=1)
        if conformal is not None and target in conformal:
            offsets = [conformal[target].get(int(h), (0.0, 0.0)) for h in horizons]
            lower = np.array([lo for lo, _ in offsets])
            upper = np.array([hi for _, hi in offsets])
            if target == TARGET_GENERATION:
                lower = np.where(daylight, lower, 0.0)
                upper = np.where(daylight, upper, 0.0)
            ordered[:, 0] -= lower
            ordered[:, 2] += upper
        ordered = np.clip(ordered, 0.0, None)
        result[target] = {q: ordered[:, i] for i, q in enumerate(QUANTILES)}
    return result


def predict_quantiles(
    models: ModelMap,
    rows: list[dict[str, float]],
    conformal: ConformalOffsets | None = None,
) -> list[dict[str, dict[Quantile, float]]]:
    """Per-row convenience wrapper over `predict_batch`."""
    batch = predict_batch(models, pd.DataFrame(rows), conformal)
    return [
        {target: {q: float(batch[target][q][i]) for q in QUANTILES} for target in TARGETS}
        for i in range(len(rows))
    ]


def fit_conformal_offsets(models: ModelMap, calibration: pd.DataFrame) -> ConformalOffsets:
    """CQR offsets for the LightGBM models — see `conformal_offsets`."""
    return conformal_offsets(predict_batch(models, calibration), calibration)


def conformal_offsets(raw: QuantilePredictions, calibration: pd.DataFrame) -> ConformalOffsets:
    """Asymmetric CQR offsets (Romano, Patterson & Candes, 2019) for any
    forecaster, from its uncalibrated predictions on held-out calibration
    rows. Each tail is calibrated on its own: the lower offset is the
    (1 - alpha/2)(1 + 1/n) empirical quantile of P10 - y, the upper one the
    same quantile of y - P90 — so about 10% of outcomes fall below P10 and
    10% above P90, not merely 80% in between with the misses all on one
    side. An offset may be negative: the band tightens where it was too
    cautious."""
    horizons = calibration["horizon_hours"].to_numpy().astype(int)
    daylight = _daylight(calibration)
    offsets: ConformalOffsets = {}
    for target in TARGETS:
        y = calibration[target].to_numpy(dtype=np.float64)
        below = raw[target]["p10"] - y
        above = y - raw[target]["p90"]
        offsets[target] = {}
        for horizon in sorted(set(horizons.tolist())):
            mask = horizons == horizon
            if target == TARGET_GENERATION:
                mask &= daylight
            n = int(mask.sum())
            if n == 0:
                offsets[target][horizon] = (0.0, 0.0)
                continue
            level = min(1.0, (1.0 - _ALPHA / 2) * (1.0 + 1.0 / n))
            offsets[target][horizon] = (
                float(np.quantile(below[mask], level)),
                float(np.quantile(above[mask], level)),
            )
    return offsets


def save_conformal(offsets: ConformalOffsets, *, artifacts_dir: Path = ARTIFACTS_DIR) -> None:
    serialisable = {
        t: {str(h): {"lower": lo, "upper": hi} for h, (lo, hi) in by_h.items()}
        for t, by_h in offsets.items()
    }
    (artifacts_dir / _CONFORMAL_FILE).write_text(json.dumps(serialisable, indent=2))


def load_conformal(*, artifacts_dir: Path = ARTIFACTS_DIR) -> ConformalOffsets | None:
    path = artifacts_dir / _CONFORMAL_FILE
    if not path.exists():
        return None
    raw: dict[str, dict[str, Any]] = json.loads(path.read_text())

    def pair(value: Any) -> tuple[float, float]:
        # Older files hold one symmetric offset per horizon.
        if isinstance(value, dict):
            return float(value["lower"]), float(value["upper"])
        return float(value), float(value)

    return {t: {int(h): pair(v) for h, v in by_h.items()} for t, by_h in raw.items()}


def pinball_loss(
    y_true: npt.NDArray[np.float64], y_pred: npt.NDArray[np.float64], alpha: float
) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(alpha * diff, (alpha - 1) * diff)))


def mean_pinball(
    y_true: npt.NDArray[np.float64], quantiles: dict[Quantile, npt.NDArray[np.float64]]
) -> float:
    """Average pinball loss across P10/P50/P90 — a single number per target."""
    return float(np.mean([pinball_loss(y_true, quantiles[q], a) for q, a in QUANTILES.items()]))


BASELINE_COLUMNS = {
    TARGET_CONSUMPTION: "lag_day_consumption_kw",
    TARGET_GENERATION: "lag_day_generation_kw",
}


def seasonal_naive_predictions(df: pd.DataFrame) -> QuantilePredictions:
    """The baseline every forecaster must beat: the same hour yesterday,
    used as all three quantiles."""
    return {
        target: dict.fromkeys(QUANTILES, df[column].to_numpy(dtype=np.float64))
        for target, column in BASELINE_COLUMNS.items()
    }


def nmae(y_true: npt.NDArray[np.float64], y_pred: npt.NDArray[np.float64]) -> float:
    """Normalised mean absolute error: mean |error| over the mean actual, so
    households (and targets) of different sizes compare."""
    scale = float(np.mean(y_true))
    return float(np.mean(np.abs(y_true - y_pred))) / scale if scale > 0 else 0.0


def score_quantiles(
    df: pd.DataFrame, predictions: QuantilePredictions
) -> dict[str, dict[str, float]]:
    """Score any forecaster's P10/P50/P90 on held-out rows, the same way for
    every model compared: mean pinball loss, nMAE of the P50, P10-P90
    coverage, and how often the actual falls below P10 and below P90 (a
    calibrated forecaster: ~10% and ~90%). Coverage and calibration count
    daylight rows only for generation: at night both sides are exactly zero
    and would look trivially perfect. nMAE needs no such mask, since
    zero-error zero-valued rows leave the ratio unchanged."""
    daylight = _daylight(df)
    report: dict[str, dict[str, float]] = {}
    for target in TARGETS:
        y_true = df[target].to_numpy(dtype=np.float64)
        q = predictions[target]
        scored = daylight if target == TARGET_GENERATION else np.ones_like(daylight)
        y = y_true[scored]
        report[target] = {
            "pinball": mean_pinball(y_true, q),
            **{
                f"pinball_{name}": pinball_loss(y_true, q[name], a) for name, a in QUANTILES.items()
            },
            "nmae_p50": nmae(y_true, q["p50"]),
            "p10_p90_coverage": float(
                np.mean((y >= q["p10"][scored] - 1e-9) & (y <= q["p90"][scored] + 1e-9))
            ),
            "below_p10": float(np.mean(y < q["p10"][scored] - 1e-9)),
            "below_p90": float(np.mean(y < q["p90"][scored] - 1e-9)),
        }
    return report


def evaluate(
    models: ModelMap, df: pd.DataFrame, conformal: ConformalOffsets | None = None
) -> dict[str, dict[str, float]]:
    """Held-out quality per target: the model and the seasonal-naive
    baseline (same hour yesterday, for all three quantiles) scored the same
    way by `score_quantiles`, and the model's skill over the baseline."""
    model = score_quantiles(df, predict_batch(models, df, conformal))
    naive = score_quantiles(df, seasonal_naive_predictions(df))
    report: dict[str, dict[str, float]] = {}
    for target in TARGETS:
        m, b = model[target], naive[target]
        report[target] = {
            "pinball_model": m["pinball"],
            "pinball_seasonal_naive": b["pinball"],
            "skill_vs_naive": 1.0 - m["pinball"] / b["pinball"] if b["pinball"] > 0 else 0.0,
            "p10_p90_coverage": m["p10_p90_coverage"],
            "below_p10": m["below_p10"],
            "below_p90": m["below_p90"],
            "nmae_model": m["nmae_p50"],
            "nmae_seasonal_naive": b["nmae_p50"],
            "nmae_improvement": 1.0 - m["nmae_p50"] / b["nmae_p50"] if b["nmae_p50"] > 0 else 0.0,
            "pinball_p10": m["pinball_p10"],
            "pinball_p50": m["pinball_p50"],
            "pinball_p90": m["pinball_p90"],
        }
    return report
