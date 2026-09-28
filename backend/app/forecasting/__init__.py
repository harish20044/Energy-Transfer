"""Short-term (1-4 hour ahead) household load/generation forecasting.

Implements the ladder from ADR-0004: a seasonal-naive baseline
(`app.forecasting.baseline`) and LightGBM quantile regression as the
production forecaster (`app.forecasting.model`), trained on synthetic data
generated straight from the pure simulator (`app.forecasting.dataset`) rather
than the live database — no household needs to have lived through a real
week before it gets a forecast.
"""

from __future__ import annotations
