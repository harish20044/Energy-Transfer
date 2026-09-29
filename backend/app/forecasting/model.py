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
from typing import Literal

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
# target -> horizon (hours) -> kW to widen the P10-P90 band by on each side.
ConformalOffsets = dict[str, dict[int, float]]

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
    horizons = features["horizon_hours"].to_numpy().astype(int)
    daylight = _daylight(features)
    result: QuantilePredictions = {}
    for target in TARGETS:
        stacked = np.column_stack(
            [np.asarray(models[(target, q)].predict(matrix), dtype=np.float64) for q in QUANTILES]
        )
        ordered = np.sort(stacked, axis=1)
        if conformal is not None and target in conformal:
            widen = np.array([conformal[target].get(int(h), 0.0) for h in horizons])
            if target == TARGET_GENERATION:
                widen = np.where(daylight, widen, 0.0)
            ordered[:, 0] -= widen
            ordered[:, 2] += widen
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
    """CQR offsets from held-out calibration rows: the (1 - alpha)(1 + 1/n)
    empirical quantile of each row's conformity score max(P10 - y, y - P90)."""
    raw = predict_batch(models, calibration)
    horizons = calibration["horizon_hours"].to_numpy().astype(int)
    daylight = _daylight(calibration)
    offsets: ConformalOffsets = {}
    for target in TARGETS:
        y = calibration[target].to_numpy(dtype=np.float64)
        scores = np.maximum(raw[target]["p10"] - y, y - raw[target]["p90"])
        offsets[target] = {}
        for horizon in sorted(set(horizons.tolist())):
            mask = horizons == horizon
            if target == TARGET_GENERATION:
                mask &= daylight
            n = int(mask.sum())
            level = min(1.0, (1.0 - _ALPHA) * (1.0 + 1.0 / n)) if n else 1.0
            offsets[target][horizon] = float(np.quantile(scores[mask], level)) if n else 0.0
    return offsets


def save_conformal(offsets: ConformalOffsets, *, artifacts_dir: Path = ARTIFACTS_DIR) -> None:
    serialisable = {t: {str(h): q for h, q in by_h.items()} for t, by_h in offsets.items()}
    (artifacts_dir / _CONFORMAL_FILE).write_text(json.dumps(serialisable, indent=2))


def load_conformal(*, artifacts_dir: Path = ARTIFACTS_DIR) -> ConformalOffsets | None:
    path = artifacts_dir / _CONFORMAL_FILE
    if not path.exists():
        return None
    raw: dict[str, dict[str, float]] = json.loads(path.read_text())
    return {t: {int(h): float(q) for h, q in by_h.items()} for t, by_h in raw.items()}


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


def evaluate(
    models: ModelMap, df: pd.DataFrame, conformal: ConformalOffsets | None = None
) -> dict[str, dict[str, float]]:
    """Held-out quality per target: mean pinball loss for the model and for
    the seasonal-naive baseline (same hour yesterday, for all three
    quantiles), the model's skill over it, and P10-P90 coverage (daylight
    only for generation — night rows are trivially "inside")."""
    predictions = predict_batch(models, df, conformal)
    baseline_columns = {
        TARGET_CONSUMPTION: "lag_day_consumption_kw",
        TARGET_GENERATION: "lag_day_generation_kw",
    }
    daylight = _daylight(df)
    report: dict[str, dict[str, float]] = {}
    for target in TARGETS:
        y_true = df[target].to_numpy(dtype=np.float64)
        naive = df[baseline_columns[target]].to_numpy(dtype=np.float64)
        model_loss = mean_pinball(y_true, predictions[target])
        naive_loss = mean_pinball(y_true, dict.fromkeys(QUANTILES, naive))
        inside = (y_true >= predictions[target]["p10"] - 1e-9) & (
            y_true <= predictions[target]["p90"] + 1e-9
        )
        if target == TARGET_GENERATION:
            inside = inside[daylight]
        report[target] = {
            "pinball_model": model_loss,
            "pinball_seasonal_naive": naive_loss,
            "skill_vs_naive": 1.0 - model_loss / naive_loss if naive_loss > 0 else 0.0,
            "p10_p90_coverage": float(inside.mean()),
            **{
                f"pinball_{q}": pinball_loss(y_true, predictions[target][q], a)
                for q, a in QUANTILES.items()
            },
        }
    return report
