"""Tier 2 of the forecasting ladder (ADR-0004): LightGBM quantile regression
as the production forecaster. Two targets (consumption, generation) x three
quantiles (P10/P50/P90) = six independently trained boosters — the standard
way to do gradient-boosted quantile regression, since each quantile is its
own pinball-loss objective rather than one model's output.

Quantile crossing — the P10 model predicting *above* the P50 model for some
row, a known artefact of training independent quantile models this way —
would occasionally tell a household "you might generate negative solar
power" if left alone. `predict_quantiles` fixes it by sorting the three
predictions into order after inference, a simple, valid rearrangement (see
Chernozhukov, Fernandez-Val & Galichon, 2010, "Quantile and Probability
Curves Without Crossing").

Evaluated with the pinball (quantile) loss, the correct scoring rule for a
quantile forecast (Gneiting & Raftery, 2007, "Strictly Proper Scoring
Rules"; standard practice in the probabilistic load-forecasting literature,
e.g. Hong & Fan, 2016) rather than plain RMSE, which doesn't actually
penalise a wrong quantile.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.forecasting.features import FEATURE_COLUMNS, TARGET_CONSUMPTION, TARGET_GENERATION

Quantile = Literal["p10", "p50", "p90"]
_QUANTILES: dict[Quantile, float] = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
_TARGETS = (TARGET_CONSUMPTION, TARGET_GENERATION)

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"

ModelMap = dict[tuple[str, Quantile], lgb.Booster]


def _model_path(target: str, quantile: Quantile, artifacts_dir: Path) -> Path:
    return artifacts_dir / f"{target}_{quantile}.txt"


def train_models(df: pd.DataFrame, *, artifacts_dir: Path = ARTIFACTS_DIR) -> ModelMap:
    """Train and save all six quantile models from a training frame built by
    `app.forecasting.dataset.generate_training_rows`."""
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    models: ModelMap = {}
    features = df[list(FEATURE_COLUMNS)]

    for target in _TARGETS:
        label = df[target]
        for quantile, alpha in _QUANTILES.items():
            train_set = lgb.Dataset(features, label=label)
            booster = lgb.train(
                {
                    "objective": "quantile",
                    "alpha": alpha,
                    "metric": "quantile",
                    "num_leaves": 15,
                    "min_data_in_leaf": 30,
                    "learning_rate": 0.08,
                    "verbose": -1,
                },
                train_set,
                num_boost_round=200,
            )
            booster.save_model(str(_model_path(target, quantile, artifacts_dir)))
            models[(target, quantile)] = booster

    return models


def load_models(*, artifacts_dir: Path = ARTIFACTS_DIR) -> ModelMap:
    """All six trained boosters, or an empty dict if any artifact is missing
    — callers treat that as "fall back to the seasonal-naive baseline"
    rather than a hard failure."""
    models: ModelMap = {}
    for target in _TARGETS:
        for quantile in _QUANTILES:
            path = _model_path(target, quantile, artifacts_dir)
            if not path.exists():
                return {}
            models[(target, quantile)] = lgb.Booster(model_file=str(path))
    return models


def predict_quantiles(models: ModelMap, row: dict[str, float]) -> dict[str, dict[Quantile, float]]:
    """One row's P10/P50/P90 for both targets — sorted into a non-crossing
    order and clamped at zero, since negative power isn't physical."""
    features = np.array([[row[col] for col in FEATURE_COLUMNS]])
    result: dict[str, dict[Quantile, float]] = {}
    for target in _TARGETS:
        raw = [float(models[(target, q)].predict(features)[0]) for q in _QUANTILES]
        p10, p50, p90 = (max(0.0, v) for v in sorted(raw))
        result[target] = {"p10": p10, "p50": p50, "p90": p90}
    return result


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, alpha: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(alpha * diff, (alpha - 1) * diff)))


def evaluate(models: ModelMap, df: pd.DataFrame) -> dict[str, dict[Quantile, float]]:
    """Held-out pinball loss per target/quantile — how good the forecast
    actually is, not just whether training finished."""
    features = df[list(FEATURE_COLUMNS)]
    result: dict[str, dict[Quantile, float]] = {}
    for target in _TARGETS:
        y_true = df[target].to_numpy()
        result[target] = {}
        for quantile, alpha in _QUANTILES.items():
            y_pred = np.asarray(models[(target, quantile)].predict(features))
            result[target][quantile] = pinball_loss(y_true, y_pred, alpha)
    return result
