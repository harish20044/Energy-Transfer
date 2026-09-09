# 4. LightGBM quantile models as the primary forecaster

- **Status:** Accepted
- **Date:** 2026-09-09
- **Supersedes:** the "Forecasting: TensorFlow/Keras LSTM / Prophet" row of the Zeroth Review stack

## Context

The system needs 15-minute-ahead forecasts of household load and PV generation, produced **per household**
and **every tick**. The reviewed stack proposed an LSTM or Prophet.

- **Prophet** is designed for business time-series with strong daily/weekly/yearly seasonality and slow
  trend change. Household load at 15-minute resolution is dominated by short-horizon autocorrelation and
  weather, exactly where Prophet is weakest.
- **LSTMs** are a reasonable choice, but on short-horizon tabular forecasting with engineered lag
  features, gradient-boosted trees consistently match or beat them, while training in seconds rather than
  minutes and needing no GPU. This machine has no discrete GPU.
- **TensorFlow** adds roughly 600 MB to the image for a model that a 2 MB library can fit better.

There is also a requirement the reviewed stack did not address. Agents must bid under uncertainty: a
household that *might* have surplus should bid differently from one that certainly will. A single point
forecast cannot express that.

## Decision

A three-tier forecasting ladder:

1. **Seasonal-naive baseline** — the value at the same time yesterday. Cheap, and the honest baseline
   that objective **O1** is measured against. A model that cannot beat it is not earning its place.
2. **LightGBM quantile regression** — the production forecaster. Separate models for the 10th, 50th and
   90th percentiles, over engineered lag, calendar and weather features, producing a **predictive
   distribution** rather than a point.
3. **PyTorch LSTM** — implemented as an **offline benchmark only**, never in the serving path, so the
   thesis carries a real comparison table instead of an assertion.

Quantile output feeds risk-aware bidding directly: agents bid against P10 when selling (conservative
about promising energy they may not have) and P90 when buying.

## Consequences

**Good**

- Faster and more accurate on this problem shape, and trains on CPU in seconds — retraining per
  household nightly is trivially affordable.
- P10/P50/P90 output makes risk-aware bidding possible, which is a genuine research contribution rather
  than a reimplementation.
- Evaluation gains a second axis: **pinball loss** for the distribution, not just nMAE for the point.
- Roughly 600 MB smaller images and a much faster CI.

**Bad / accepted**

- Trees do not extrapolate beyond the training range, so an unprecedented consumption spike is
  underestimated. Acceptable because the grid safety layer — not the forecaster — is what guarantees
  physical feasibility.
- Three models per household per target instead of one. Mitigated by how cheap LightGBM training is, and
  by a model registry that keeps versioning and rollback explicit.
