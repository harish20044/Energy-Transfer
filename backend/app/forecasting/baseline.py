"""Tier 1 of the forecasting ladder (ADR-0004): same hour, one day ago. No
training, no model — the honest floor a real forecaster must beat, and the
fallback whenever trained quantile models aren't available in an
environment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaselineForecast:
    consumption_kw: float
    generation_kw: float


def seasonal_naive(lag_24h_consumption_kw: float, lag_24h_generation_kw: float) -> BaselineForecast:
    return BaselineForecast(
        consumption_kw=lag_24h_consumption_kw, generation_kw=lag_24h_generation_kw
    )
