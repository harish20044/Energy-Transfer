"""LightGBM quantile models: trained artifacts round-trip through disk, and
predictions never cross quantiles or go negative — the two properties
`app.forecasting.model` exists to guarantee on top of raw LightGBM output."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.forecasting.dataset import HouseholdConfig, generate_training_rows
from app.forecasting.features import FEATURE_COLUMNS
from app.forecasting.model import evaluate, load_models, pinball_loss, predict_quantiles, train_models

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def trained_df() -> pd.DataFrame:
    configs = (HouseholdConfig(household_id="h1", member_count=4, solar_capacity_kwp=5.0),)
    rows = generate_training_rows(configs, num_days=4, seed=42)
    return pd.DataFrame(rows)


def test_predictions_never_cross_quantiles_or_go_negative(
    tmp_path: Path, trained_df: pd.DataFrame
) -> None:
    models = train_models(trained_df, artifacts_dir=tmp_path)
    sample_row = {col: trained_df.iloc[0][col] for col in FEATURE_COLUMNS}

    quantiles = predict_quantiles(models, sample_row)

    for target_quantiles in quantiles.values():
        assert target_quantiles["p10"] <= target_quantiles["p50"] <= target_quantiles["p90"]
        assert target_quantiles["p10"] >= 0.0


def test_loaded_models_predict_identically_to_the_trained_ones(
    tmp_path: Path, trained_df: pd.DataFrame
) -> None:
    trained = train_models(trained_df, artifacts_dir=tmp_path)
    loaded = load_models(artifacts_dir=tmp_path)
    sample_row = {col: trained_df.iloc[0][col] for col in FEATURE_COLUMNS}

    assert predict_quantiles(trained, sample_row) == predict_quantiles(loaded, sample_row)


def test_load_models_returns_empty_when_artifacts_are_missing(tmp_path: Path) -> None:
    assert load_models(artifacts_dir=tmp_path) == {}


def test_evaluate_returns_a_loss_for_every_target_and_quantile(
    tmp_path: Path, trained_df: pd.DataFrame
) -> None:
    models = train_models(trained_df, artifacts_dir=tmp_path)

    metrics = evaluate(models, trained_df)

    assert set(metrics) == {"consumption_kw", "generation_kw"}
    for quantile_losses in metrics.values():
        assert set(quantile_losses) == {"p10", "p50", "p90"}
        assert all(loss >= 0.0 for loss in quantile_losses.values())


def test_pinball_loss_is_zero_for_a_perfect_prediction() -> None:
    y = np.array([1.0, 2.0, 3.0])

    assert pinball_loss(y, y, alpha=0.1) == pytest.approx(0.0)
