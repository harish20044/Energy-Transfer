# Evaluation: objectives O1–O7

Generated 2026-10-07T13:14:17+00:00 by `python -m app.evaluation` (seed 42, 4 min). Every figure below is measured, not assumed: the harness runs the app's own forecaster, agents, market, grid safety layer and delivery code in memory, on a fixed suite of seeded sessions. Targets are the ones set in [objectives.md](objectives.md).

## Results at a glance

| Objective | Target | Result | |
|---|---|---|---|
| **O1** Forecasting | nMAE at least 25% below same-hour-yesterday; P10 and P90 calibrated (10% ± 3 pp of actuals below P10, 90% ± 3 pp below P90) | nMAE 29.1% lower for load, 45.0% for solar · below P10: 9.9% / 11.4% · below P90: 89.7% / 91.7% | **Met** |
| **O2** Matching efficiency | ≥ 95% of the saving a hindsight-optimal schedule could have made | 54.5% (₹1,345.35 of ₹2,468.40) | **Not met** |
| **O3** Autonomy and speed | Every slot clears and settles unattended; clearing an hour for 100 homes takes p95 < 200 ms | 100% of slots unattended · p95 411 ms at 100 homes (28 ms at 10) | **Not met** |
| **O4** Grid safety | Zero violations in the settled allocation, by the fast linear check and by full AC power flow | 0 linear · 0 AC (136 slots checked, 286 curtailments) | **Met** |
| **O5** Renewable use | EB export at least 30% lower than EB-only; self-sufficiency and self-consumption both up | export 14.0% lower · self-sufficiency 53.6% → 61.1% · self-consumption 65.6% → 70.4% | **Not met** |
| **O6** Economic benefit | Bill reduction ≥ 10% (band 10–20%), bill-weighted over net buyers; no household worse off than EB-only | 4.4% bill-weighted reduction (median 3.9%) · 10 of 120 household-sessions worse off (worst −₹7.56) | **Not met** |
| **O7** Explainability | 100% of trades carry both parties' decision record and rationale | 100% of 1,033 trades · 4,080 of 4,080 decisions | **Met** |

**3 of 7 objectives met.** Where a target is missed, the gap is reported as found.

## The suite

Twelve 24-hour sessions from 6 am on the ten seeded homes, run in order with the agents' learned memory carried from one to the next, plus one 12-hour session on a 100-home feeder for the scale test. *Mixed* is the plan page's preset: three homes with no panels and no battery, three with a 15 kWh battery.

| Session | P2P units | Efficiency (O2) | EB export cut (O5) | Community saving | Worst home | Trades explained |
|---|---|---|---|---|---|---|
| Jan · identical homes | 0.0 | 0.0% | 0.0% | ₹0.00 | ₹0.00 | 0/0 |
| Jan · mixed | 25.1 | 67.6% | 10.1% | ₹189.96 | ₹3.65 | 73/73 |
| Mar · family what-ifs | 6.3 | 35.2% | 3.8% | ₹48.39 | ₹0.00 | 13/13 |
| Apr · clear sky, mixed | 44.0 | 49.5% | 52.5% | ₹227.78 | ₹6.14 | 69/69 |
| May · identical homes | 9.3 | 66.5% | 31.1% | ₹54.07 | ₹0.29 | 17/17 |
| May · mixed | 36.8 | 63.1% | 67.1% | ₹176.17 | −₹1.99 | 46/46 |
| May · heatwave, mixed | 27.4 | 55.9% | 79.5% | ₹119.26 | −₹0.56 | 28/28 |
| Jun · clear, mixed, +20% peak | 18.8 | 28.0% | 46.5% | ₹84.76 | ₹0.00 | 21/21 |
| Jul · broken cloud, mixed | 33.5 | 59.3% | -75.4% | ₹105.25 | −₹7.56 | 42/42 |
| Oct · monsoon rain, mixed | 31.6 | 52.2% | -500.9% | ₹238.73 | −₹2.62 | 64/64 |
| Nov · mixed, EB cut 7-9 pm | 35.0 | 74.1% | 10.5% | ₹225.93 | −₹2.82 | 83/83 |
| Dec · identical, +20% peak | 0.6 | 12.5% | 0.7% | ₹3.94 | ₹0.00 | 1/1 |
| May · 100 homes, mixed | 229.1 | 41.3% | 31.0% | ₹1,613.12 | ₹0.00 | 576/576 |

## O1 · Forecasting

Scored on the 73 held-out test days of the forecaster's training year (70,080 rows, every horizon from 1 to 24 hours), which no model saw while training or calibrating. Every model is scored by the same function (`app.forecasting.model.score_quantiles`). Pinball loss and nMAE: lower is better. Coverage and calibration count daylight hours only for solar.

| Model | Target | Pinball (kW) | nMAE of P50 | P10–P90 coverage | Below P10 | Below P90 |
|---|---|---|---|---|---|---|
| Same hour yesterday (baseline) | Load | 0.1501 | 0.407 | 0.0% | 50.0% | 50.0% |
| Same hour yesterday (baseline) | Solar | 0.1036 | 0.263 | 0.0% | 54.1% | 54.1% |
| LightGBM, raw quantiles | Load | 0.0673 | 0.288 | 71.8% | 14.5% | 86.3% |
| LightGBM, raw quantiles | Solar | 0.0411 | 0.145 | 55.0% | 23.2% | 78.2% |
| LightGBM + conformal calibration (served) | Load | 0.0671 | 0.288 | 79.8% | 9.9% | 89.7% |
| LightGBM + conformal calibration (served) | Solar | 0.0394 | 0.145 | 80.2% | 11.4% | 91.7% |
| LSTM, raw quantiles | Load | 0.0812 | 0.339 | 78.3% | 9.9% | 88.1% |
| LSTM, raw quantiles | Solar | 0.0398 | 0.162 | 79.3% | 13.6% | 92.9% |
| LSTM + conformal calibration | Load | 0.0811 | 0.339 | 79.1% | 10.4% | 89.5% |
| LSTM + conformal calibration | Solar | 0.0398 | 0.162 | 80.9% | 11.9% | 92.8% |

The LSTM (LSTM(24 h of load and solar, hidden 64) + target-hour features -> P10/P50/P90 x 2, 23,622 parameters, 12 epochs, 6 min on CPU, PyTorch 2.14.1+cu130) is trained on the same training days and calibrated on the same calibration days as LightGBM (`app.evaluation.lstm`). It is an offline benchmark and is never served.

## O2 · Matching efficiency

The benchmark is the best any mechanism could have done: a linear program (`app.evaluation.optimum`) that knows every home's actual load and solar in advance and schedules every battery, every neighbour exchange and every EB import and export, within the same battery physics and the same grid constraints the safety layer enforces. Payments between neighbours are transfers, so community welfare is the community's net EB bill (plus ₹50 per unserved unit, minus charge left in the batteries at the feed-in tariff). Efficiency is the share of the achievable saving over EB-only that the agents captured: (EB-only − actual) / (EB-only − optimum), pooled over the suite. The gap is the price of committing hours ahead on forecasts, in hourly blocks, instead of knowing the future.

| Session | EB-only | Agents | Hindsight optimum | Efficiency |
|---|---|---|---|---|
| Jan · identical homes | −₹511.90 | −₹511.90 | −₹530.84 | 0.0% |
| Jan · mixed | −₹63.97 | −₹213.19 | −₹284.55 | 67.6% |
| Mar · family what-ifs | −₹206.98 | −₹245.97 | −₹317.62 | 35.2% |
| Apr · clear sky, mixed | ₹1,116.70 | ₹900.35 | ₹679.25 | 49.5% |
| May · identical homes | ₹1,180.58 | ₹1,126.51 | ₹1,099.29 | 66.5% |
| May · mixed | ₹1,869.04 | ₹1,713.67 | ₹1,622.64 | 63.1% |
| May · heatwave, mixed | ₹2,120.68 | ₹2,001.42 | ₹1,907.43 | 55.9% |
| Jun · clear, mixed, +20% peak | ₹1,891.08 | ₹1,806.32 | ₹1,588.84 | 28.0% |
| Jul · broken cloud, mixed | ₹1,579.26 | ₹1,510.89 | ₹1,463.93 | 59.3% |
| Oct · monsoon rain, mixed | ₹409.73 | ₹274.30 | ₹150.37 | 52.2% |
| Nov · mixed, EB cut 7-9 pm | ₹217.00 | −₹102.59 | −₹214.44 | 74.1% |
| Dec · identical, +20% peak | −₹319.98 | −₹323.93 | −₹351.46 | 12.5% |

## O3 · Autonomy and speed

Latency is wall-clock time to clear one hourly slot: every agent's decision graph runs, households negotiate, the auction clears and grid safety checks the result. Forecasting happens once per session, before the first slot, and is reported separately.

| Feeder | Slots | p50 | p95 | Max | Forecasting, whole session |
|---|---|---|---|---|---|
| 10 homes (suite) | 288 | 15 ms | 28 ms | 37 ms | 0.9 s per session |
| 100 homes | 12 | 270 ms | 411 ms | 421 ms | 6.4 s |

Autonomy: 100% of planned slots cleared and were delivered with no human input; 0 sessions failed.

## O4 · Grid safety

Every settled slot is re-checked twice: by the same linearised DistFlow the safety layer uses, and by a full AC power flow (pandapower, Newton–Raphson; `app.evaluation.ac_check`) on the same feeder and the same injections, with line reactance the linear model ignores. The injections are the safety layer's own model: the settled neighbour trades.

| Feeder | Slots AC-checked | Curtailments | Max line loading (linear / AC) | Lowest voltage (linear / AC) | Highest voltage (linear / AC) | Violations (linear / AC) |
|---|---|---|---|---|---|---|
| 10 homes (suite) | 124 | 0 | 31% / 30% | 0.984 / 0.983 pu | 1.031 / 1.030 pu | 0 / 0 |
| 100 homes | 12 | 286 | 23% / 22% | 0.965 / 0.962 pu | 1.034 / 1.030 pu | 0 / 0 |

Largest gap between the linear and AC voltage at any bus: 0.0051 pu. Statutory band: 0.95–1.05 pu.

## O5 · Renewable use and O6 · Economic benefit

Both are measured against the same counterfactual: the same hours, the same weather and families, with each home dealing only with the EB (its battery still doing self-consumption). Self-sufficiency = load met without the EB / total load. Self-consumption = local solar used locally / total solar.

- EB export over the suite: 701 units EB-only, 603 with neighbours trading.
- Bill reduction is averaged over the 58 household-sessions that are net buyers on an EB-only bill, weighted by that bill — total saving over total bill, since a plain mean of percentages is ruled by near-zero bills (and a percentage of a negative bill means nothing). Net sellers' gains are in the community saving of ₹1,474.25 over the suite.

## What these results do not show

- **Synthetic data.** Every session runs on the calibrated Chennai simulator ([ADR-0007](adr/0007-calibrated-synthetic-chennai-data.md)), not metered homes.
- **The grid model counts neighbour trades only.** The safety layer and both checks load the feeder with the settled P2P exchanges, not each home's whole net load; the EB's own supply is the distribution company's to plan.
- **One suite.** Twelve sessions cover the seasons, weathers and what-ifs a user can set, but they are one seed. Results on other seeds will differ in the details.

## Reproduce

```
docker exec energy-backend python -m app.evaluation          # this report
docker compose --profile bench run --rm bench                 # the LSTM benchmark
```
