# 10. Hourly forecasts 1–24 hours ahead, with conformally calibrated quantiles

- **Status:** Accepted
- **Date:** 2026-10-06
- **Refines:** [ADR-0004](0004-lightgbm-over-deep-learning.md)

## Context

ADR-0004 chose LightGBM quantile models for a 15-minute-ahead forecast, run every tick. Planning sessions
([ADR-0008](0008-planning-sessions-with-the-eb-as-provider.md)) need something different: each home's load
and solar for every hour of a 4- to 24-hour horizon, forecast before the first slot clears.

The raw quantile models also under-cover. On held-out days, 77.0% of actual load and 67.1% of actual
daylight solar fell inside P10–P90, against a nominal 80%. Agents size commitments from that band
([ADR-0009](0009-newsvendor-agents-in-the-calibrated-band.md)), so a band that is too narrow makes them
over-confident.

## Decision

**Target and features** (`app/forecasting/features.py`)

Hourly mean load and generation in kW, with the horizon h = 1…24 as a feature, so one model serves every
horizon. The features are:

- hour of day, weekend, and season as the sine and cosine of the day of year;
- the family's make-up (members, occupied bedrooms, workers away, night shift, students, elderly, people
  home by day) and the what-ifs (guests, family away, work from home);
- panel size, the temperature forecast, clear-sky PV for the hour and recent clearness;
- the same hour yesterday, and the last one and two hours.

**Training data** (`dataset.py`): 365 synthetic days × 10 homes ([ADR-0007](0007-calibrated-synthetic-chennai-data.md)).

- 20% of days use what-if weather and 15% of home-days carry family overrides, so the model has seen the
  conditions a user can set.
- Each forecast origin contributes four horizons, sampled from the bands 1–3, 4–8, 9–15 and 16–24 hours.

**Split by whole day** (day of year mod 5): one fifth to test, one fifth to calibrate, the rest to train.
That gives 210,240 rows to train, 70,080 to calibrate and 70,080 to test. No hour of a test day is ever
seen in training.

**Models:** six LightGBM boosters (P10, P50 and P90 for load and for solar), 300 rounds each.

- Predicted quantiles are sorted so they cannot cross (Chernozhukov, Fernández-Val & Galichon, 2010).
- Conformalized quantile regression (Romano, Patterson & Candès, 2019) adjusts the P10–P90 band by an
  offset measured on the calibration days. There is one offset per target and per horizon, since
  uncertainty grows with lead time.

**Results** on the test days:

| | Load | Solar (daylight) |
|---|---|---|
| P10–P90 coverage, raw | 77.0% | 67.1% |
| P10–P90 coverage, calibrated | 79.7% | 78.5% |
| Pinball loss vs same hour yesterday | 52.7% lower | 62.6% lower |

## Consequences

**Good**

- One model family serves every horizon the user can choose, and trains on a CPU with no GPU.
- The band agents commit from is calibrated to the coverage it claims, close to the 80% target.
- Skill is reported against the seasonal-naive baseline that ADR-0004 named as the bar to beat.

**Bad / accepted**

- **The PyTorch LSTM benchmark that ADR-0004 planned was not built.** The thesis comparison table has
  LightGBM against seasonal-naive only.
- Objective O1 targets nMAE 25% below seasonal-naive. Pinball skill is reported, but nMAE is not
  computed yet. It belongs in the evaluation harness, which does not exist yet.
- Training panel derate runs only to 0.4, while a user can set 1.0 (no panels). In practice the solar
  forecast for such a home is zero, as observed in the October session, but no test pins that
  behaviour.
- Every score is on synthetic data, so it measures how learnable the simulator is.
