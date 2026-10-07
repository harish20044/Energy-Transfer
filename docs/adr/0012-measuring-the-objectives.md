# 12. Measuring the objectives: an in-memory harness, a hindsight optimum and an AC check

- **Status:** Accepted
- **Date:** 2026-10-07

## Context

[objectives.md](../objectives.md) turns each objective into a number with a target. Until now none of
them was measured end to end. Three pieces the objectives assume did not exist:

- the evaluation harness that produces the O1–O7 table;
- the offline optimum that O2 compares against;
- the full AC power flow that O4 uses to confirm the linearised grid check.

A fourth, the LSTM benchmark promised by [ADR-0004](0004-lightgbm-over-deep-learning.md), was also missing.

A harness is only worth its numbers if it measures the system that runs, not a copy of it.

## Decision

**One code path.** The hour-by-hour clearing moved out of `plan_session` into a pure `SessionMarket`
(`app/engine/market_run.py`), and preparing a household for a session into `prepare_household`. The app
persists what they produce; the harness (`app/evaluation/`) runs them directly, in memory. Delivery uses
the same `deliver` function as "Next hour". Households are the seeded homes, built without a database.

**A fixed suite** (`app/evaluation/suite.py`). There are twelve 24-hour sessions from 6 am on the ten seeded
homes, covering:

- every season and every weather scenario;
- identical and mixed neighbourhoods, and family what-ifs;
- an evening EB power cut;
- a 20% evening peak surcharge.

They run in order, with the agents' memory carried across. There is also one 12-hour session on a 100-home
feeder for the scale test.

**O1** regenerates exactly the forecaster's held-out test days. Every model is scored by one function,
`score_quantiles`: pinball loss, nMAE of the P50, P10–P90 coverage, and the share of actuals below P10 and
below P90. The models are:

- seasonal-naive;
- LightGBM, raw and calibrated;
- the LSTM (`app/evaluation/lstm.py`, PyTorch). The LSTM is trained on the same training days, calibrated
  on the same calibration days, and runs in its own image (`docker compose --profile bench run --rm bench`)
  so the app's image stays small.

"Calibrated" is taken as within ±3 percentage points of 10% below P10 and 90% below P90.

**O2** compares the agents with a hindsight-optimal linear program (`app/evaluation/optimum.py`, HiGHS).

- It knows every home's actual load and solar, and schedules every battery, neighbour exchange and EB
  flow.
- It works within the same battery model and the same thermal and voltage constraints the safety layer
  enforces.
- Community welfare is the net EB bill, since neighbour payments are transfers. Unserved energy is valued
  at ₹50 per unit. Charge left in the batteries is credited at the feed-in tariff, so draining batteries
  doesn't count as a saving.
- Efficiency is (EB-only − agents) / (EB-only − optimum), pooled over the suite.
- The agents' own operation is a feasible point of the LP, so the optimum can never cost more. The tests
  check this.

**O3** times each slot's clearing: every agent's decision, the negotiation, the auction and the grid
check. It reports p50 and p95 at 10 and at 100 homes. Autonomy is the share of planned slots that cleared
and were delivered with no input.

**O4** re-checks every settled slot twice:

- with the linearised DistFlow;
- with a full AC Newton–Raphson load flow in pandapower (`app/evaluation/ac_check.py`), on the same feeder
  and injections. Line reactance uses an X/R ratio of 0.25 on a 1 kVA, 0.415 kV base, the base the linear
  model's arithmetic implies.

**O5 and O6** compare each session with an EB-only replay of the same hours, as the app's statements do.

- O5 uses community export, self-sufficiency and self-consumption.
- O6 uses each household's bill. The mean reduction is taken over net buyers, because a percentage of a
  negative bill is meaningless. Individual rationality is checked for every household-session, with a
  1-paisa tolerance.

**O7** counts trades for which both parties have a stored decision with a message, its reasons and an
outcome.

`python -m app.evaluation` writes `docs/evaluation.md` and `docs/evaluation.json`. A missed target is
reported as found.

**Two forecaster changes the measurement led to**, both tuned on the calibration days and never on the
test days:

- **Asymmetric conformal calibration.** Each tail is now calibrated on its own. Before, solar's P10–P90
  band covered about 80% of actuals, but 14.9% fell below P10 against a nominal 10%.
- **1,500 boosting rounds instead of 300.** The load P50's error against same-hour-yesterday kept falling:
  24.8% better at 300 rounds, 29.4% at 1,500.

**Changes to the system the measurement led to:**

- **Grid voltage margin.** The full AC check found 22 voltage violations on the 100-home feeder that the
  linear check had passed: curtailing to exactly 0.950 pu by the linear estimate left buses at 0.939 pu.
  The safety layer now keeps 0.015 pu inside the statutory band, just over the worst measured
  linear-vs-AC gap of 0.013 pu. The violations went to zero.
- **Firm sales sized on the whole path.** On a cloudy day the median forecast filled a battery by noon that
  never filled, and homes sold "surplus" they later bought back at retail. Sellers now walk the battery
  with the forecast at their commitment quantile all session.
- **No sun, no solar.** A home with no panels was forecast 0.000008 kW. Solar is now exactly zero
  wherever clear-sky potential is zero.
- **Rejected after measuring:** judging spare stored charge on the cautious (P10 sun, P90 load) view. It cut
  the community's saving by about a third, so it was not kept.

**Targets revised after measuring.** O2 now applies its 95% target to the auction's allocative efficiency
on the submitted orders (`app/evaluation/allocative.py`). The perfect-foresight share stays in the report,
with no target. O5's target is now 30% of the largest export cut physically possible: no schedule can cut
this suite's export by more than about 43%. O6 is judged per household over the whole evaluation period,
with losing days counted and reported. The reasons are in
[objectives.md, Revisions](../objectives.md#revisions).

This supersedes the results table in [ADR-0010](0010-hourly-forecasts-with-conformal-calibration.md).
The current figures are in [evaluation.md](../evaluation.md).

## Consequences

**Good**

- Every number in the thesis table is reproducible from one command and one seed, and comes from the code
  the demo runs.
- O2's benchmark answers the objectives' own question: how far real-time clearing under uncertainty falls
  short of perfect foresight.
- The AC check measures how far the linearised grid model can be trusted, instead of asserting it.

**Bad / accepted**

- One seed, one suite. The suite covers what a user can set, but the results are one sample.
- The ₹50 value of lost load and the feed-in value of leftover charge are modelling choices. They only
  affect sessions with a power cut, and they apply identically to all three schedules compared.
- The grid model still counts only neighbour trades, not each home's whole net load. Both checks inherit
  that limit.
