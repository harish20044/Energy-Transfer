"""LightGBM quantile models: artifacts round-trip through disk, predictions
never cross or go negative, conformal offsets widen the band and restore
coverage, and evaluation reports skill against the naive baseline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.features import FEATURE_COLUMNS
from app.forecasting.model import (
    evaluate,
    fit_conformal_offsets,
    load_conformal,
    load_models,
    pinball_loss,
    predict_batch,
    predict_quantiles,
    save_conformal,
    train_models,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    configs = (HouseholdConfig("h1", 4, 5.0), HouseholdConfig("h4", 2, 5.0))
    return pd.DataFrame(
        generate_training_rows(configs, start=date(2025, 5, 1), num_days=4, seed=42)
    )


@pytest.fixture(scope="module")
def trained(frame: pd.DataFrame, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    path = tmp_path_factory.mktemp("models")
    return path, train_models(frame, artifacts_dir=path, boost_rounds=30)


def test_predictions_never_cross_quantiles_or_go_negative(
    frame: pd.DataFrame, trained: tuple
) -> None:
    _, models = trained
    batch = predict_batch(models, frame)
    for target in batch.values():
        assert (target["p10"] <= target["p50"] + 1e-12).all()
        assert (target["p50"] <= target["p90"] + 1e-12).all()
        assert (target["p10"] >= 0).all()


def test_loaded_models_predict_identically(frame: pd.DataFrame, trained: tuple) -> None:
    path, models = trained
    row = [{col: float(frame.iloc[0][col]) for col in FEATURE_COLUMNS}]
    assert predict_quantiles(load_models(artifacts_dir=path), row) == predict_quantiles(models, row)


def test_load_models_returns_empty_when_artifacts_are_missing(tmp_path: Path) -> None:
    assert load_models(artifacts_dir=tmp_path) == {}
    assert load_conformal(artifacts_dir=tmp_path) is None


def test_conformal_offsets_move_coverage_to_the_nominal_eighty_percent(
    frame: pd.DataFrame, trained: tuple, tmp_path: Path
) -> None:
    """CQR widens an overconfident band and narrows an over-wide one: on the
    calibration rows themselves, coverage lands at (or just above) 80%."""
    _, models = trained
    offsets = fit_conformal_offsets(models, frame)
    save_conformal(offsets, artifacts_dir=tmp_path)
    assert load_conformal(artifacts_dir=tmp_path) == offsets
    raw = evaluate(models, frame)
    calibrated = evaluate(models, frame, offsets)
    for target in raw:
        cal = calibrated[target]["p10_p90_coverage"]
        assert cal >= 0.79
        assert abs(cal - 0.8) <= abs(raw[target]["p10_p90_coverage"] - 0.8) + 0.02


def test_evaluation_reports_skill_against_the_naive_baseline(
    frame: pd.DataFrame, trained: tuple
) -> None:
    _, models = trained
    report = evaluate(models, frame)
    assert set(report) == {"consumption_kw", "generation_kw"}
    for metrics in report.values():
        assert metrics["pinball_model"] >= 0
        assert "skill_vs_naive" in metrics
        assert 0.0 <= metrics["p10_p90_coverage"] <= 1.0


def test_pinball_loss_is_zero_for_a_perfect_prediction() -> None:
    y = np.array([1.0, 2.0, 3.0])
    assert pinball_loss(y, y, alpha=0.1) == pytest.approx(0.0)


def test_pinball_loss_penalises_under_prediction_more_at_high_quantiles() -> None:
    y = np.array([2.0])
    low = np.array([1.0])
    assert pinball_loss(y, low, alpha=0.9) > pinball_loss(y, low, alpha=0.1)
