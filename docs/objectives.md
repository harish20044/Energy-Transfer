# Objectives and how they are measured

The Zeroth Review stated directional outcomes ("accurate forecasting", "efficient matching"). Those
cannot be passed or failed. This document turns each into something falsifiable, with a formula, a
baseline and a target.

Every number is produced by the evaluation harness (`scripts/evaluate.py`, phase P6) from a single
seeded run, so the table below regenerates identically on any machine.

---

## O1 · Accurate short-term forecasting

**Measures:** 15-minute-ahead household load and PV generation.

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
2. **Latency** — wall-clock time from gate close to settled allocation, at 100 agents.
   **Target: p95 < 200 ms.**

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

**Target: holds for every household, in every tick.** This is structurally guaranteed by bounding the
clearing price to `[feed_in_tariff, retail_tariff]` — a seller never accepts less than the utility would
pay, a buyer never pays more than the utility would charge — and it is verified by property test rather
than assumed. Startup configuration validation rejects an inverted tariff band outright, because it would
make the guarantee unachievable.

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
