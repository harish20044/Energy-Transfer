# Objectives and how they are measured

The Zeroth Review stated directional outcomes ("accurate forecasting", "efficient matching"). Those
cannot be passed or failed. This document turns each into something falsifiable, with a formula, a
baseline and a target.

Every number comes from the evaluation harness, `python -m app.evaluation`
([ADR-0012](adr/0012-measuring-the-objectives.md)), run over a fixed suite of seeded sessions, so the table
regenerates identically on any machine. **Measured results: [evaluation.md](evaluation.md).**

---

## O1 · Accurate short-term forecasting

**Measures:** hourly household load and PV generation, 1 to 24 hours ahead, the horizon a planning
session needs ([ADR-0010](adr/0010-hourly-forecasts-with-conformal-calibration.md)).

**Point accuracy** — normalised mean absolute error, so households of different sizes are comparable:

$$\text{nMAE} = \frac{\frac{1}{n}\sum_{t=1}^{n}|y_t - \hat{y}_t|}{\bar{y}}$$

**Distribution accuracy** — pinball (quantile) loss, which is what actually matters for risk-aware
bidding, since a P10 forecast that is confidently wrong is worse than a wide honest one:

$$L_\tau(y, \hat{y}) = \begin{cases} \tau(y - \hat{y}) & y \geq \hat{y} \\ (1-\tau)(\hat{y} - y) & y < \hat{y} \end{cases}$$

evaluated at τ ∈ {0.1, 0.5, 0.9}.

| Compared against | |
|---|---|
| **Seasonal-naive** (same time yesterday) | the honest baseline — a model that cannot beat this is not earning its place |
| **PyTorch LSTM** | offline benchmark only, for the comparison table ([ADR-0004](adr/0004-lightgbm-over-deep-learning.md)) |

**Target: nMAE at least 25% below seasonal-naive**, with calibrated quantiles (P10 covers ~10% of
outcomes, P90 ~90%).

---

## O2 · Efficient P2P matching

**Measures:** how much of the achievable value the auction actually captures.

Social welfare of an allocation is the total surplus created — for each matched trade, the buyer's
valuation minus the seller's cost:

$$W = \sum_{\text{trades}} (v_{\text{buyer}} - c_{\text{seller}}) \cdot q$$

The benchmark is the **offline optimum**: a linear program solved with perfect hindsight over the same
interval, maximising welfare subject to the same grid constraints. That is the best any mechanism could
have done.

$$\text{Allocative efficiency} = \frac{W_{\text{auction}}}{W_{\text{optimal}}}$$

**Target: ≥95%.** The gap is the price of clearing in real time under uncertainty instead of knowing the
future — quantifying it is a result in itself.

---

## O3 · Autonomous trading

Two things must both hold:

1. **Autonomy** — the fraction of ticks that clear and settle with no human input. **Target: 100%.**
2. **Latency** — wall-clock time to clear one hourly slot of a planning session (agent decisions,
   negotiation, grid safety), at 100 agents. **Target: p95 < 200 ms.**

Latency is measured with a Prometheus histogram over the clearing path only, excluding LLM explanation
generation, which is asynchronous by design.

---

## O4 · Safe energy allocation

**Measures:** grid constraint violations in the *final, settled* allocation.

Checked per tick, per constraint:

| Constraint | Condition |
|---|---|
| Line thermal | $\|I_{ij}\| \le I_{ij}^{\max}$ for every line |
| Transformer | $\|P_{\text{feeder}}\| \le$ `TRANSFORMER_CAPACITY_KW` |
| Voltage | $V^{\min} \le \|V_i\| \le V^{\max}$ (default 0.95–1.05 p.u.) at every bus |

**Target: exactly 0.** Not "few" — zero. This is an invariant, not a metric, and it is enforced two ways:

- The Grid Safety agent holds **veto power** and curtails until the allocation is feasible.
- A **Hypothesis property test** generates thousands of random microgrid configurations — including
  adversarial ones, with extreme surplus concentrated at the feeder edge — and asserts no output ever
  violates a constraint.

A full AC power flow (pandapower Newton-Raphson) re-verifies a sample of ticks, confirming the fast
linearized check used in the hot path never admitted a violation the linearization hid.

---

## O5 · Improved renewable utilisation

Two standard energy-community ratios:

$$\text{SSR} = \frac{\text{load met from local generation}}{\text{total load}} \qquad
\text{SCR} = \frac{\text{local generation consumed locally}}{\text{total generation}}$$

**Target: grid export reduced by ≥30%** versus the grid-only baseline, with SSR and SCR both rising.
This is the objective that speaks directly to the problem statement — surplus renewable energy being
wasted.

---

## O6 · Economic benefit

**Measures:** whether participants are actually better off.

Per household, the bill under P2P trading versus the same demand and generation served entirely by the
utility (buy at retail, export at feed-in).

**Target: mean bill reduction of 10–20%.**

But the mean can hide someone being made worse off, so a second and stricter condition applies —
**individual rationality**:

$$\forall h \in \text{households}: \quad \text{bill}^{\text{P2P}}_h \le \text{bill}^{\text{grid-only}}_h$$

This holds at two levels, and they need different evidence.

- **Per trade: structural.** Every trade clears inside `[feed_in_tariff, retail_tariff]`. A seller never
  accepts less than the utility would pay, and a buyer never pays more than it would charge. A property
  test verifies this rather than assuming it. Startup configuration validation rejects an inverted tariff
  band outright, because it would make the guarantee unachievable.
- **Per session: empirical.** Agents commit hours ahead under forecast uncertainty
  ([ADR-0009](adr/0009-newsvendor-agents-in-the-calibrated-band.md)). A hedge that turns out not to be
  needed, or a forecast miss, can leave a household's whole-session bill above its EB-only bill, even
  though every trade was in the band. Each session statement reports the EB-only comparison per
  household. **Target: no household worse off in the evaluation sessions**, measured, not assumed.

---

## O7 · Explainability

**Measures:** the fraction of settled trades carrying **both**

1. a **machine-readable** decision record — inputs, forecast quantiles, battery state, reservation price,
   and the binding constraint if any; and
2. a **natural-language rationale** a homeowner can read.

**Target: 100%.** The machine-readable half is produced deterministically in the trading path and is
therefore always present. The natural-language half is generated asynchronously by the LLM; when the
provider is unavailable a deterministic template renders the same decision record, so coverage stays at
100% regardless ([ADR-0005](adr/0005-llm-beside-the-critical-path.md)).

---

## Traceability to the Zeroth Review

| Slide 4 objective | Measured by |
|---|---|
| Direct energy exchange between prosumers and consumers | **O2**, **O5** |
| AI agents for intelligent buyer–seller matching and trading | **O3** |
| Dynamically balance energy generation and demand | **O1**, **O4** |
| Reduce surplus energy wastage, improve microgrid efficiency | **O5**, **O6** |
| *(added)* Explainable, auditable decisions | **O7** |
