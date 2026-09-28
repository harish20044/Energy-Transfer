"""Tier 1 of the forecasting ladder: same hour, one day ago."""

from __future__ import annotations

import pytest

from app.forecasting.baseline import seasonal_naive

pytestmark = pytest.mark.unit


def test_seasonal_naive_echoes_yesterdays_reading() -> None:
    forecast = seasonal_naive(lag_24h_consumption_kw=1.5, lag_24h_generation_kw=2.5)

    assert forecast.consumption_kw == 1.5
    assert forecast.generation_kw == 2.5
