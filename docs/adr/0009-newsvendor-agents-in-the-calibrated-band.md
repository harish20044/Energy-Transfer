# 9. Agents commit as newsvendors, inside the forecast's calibrated band

- **Status:** Accepted
- **Date:** 2026-10-06

## Context

In a planning session ([ADR-0008](0008-planning-sessions-with-the-eb-as-provider.md)) each home's agent
promises energy to neighbours, or asks for it, an hour or more before delivery. The forecast is a band,
P10 to P90. The agent has to decide how much of that band to commit.

The two ways to be wrong cost different amounts.

- **Over-promising.** A seller who promises more than it generates buys the gap from the EB at retail.
- **Under-promising.** A seller who holds back exports the rest at feed-in.

For a buyer the costs are mirrored. This is the newsvendor problem. Bitar et al. (2012) applied it to
committing wind energy into a forward market.

**Incident, 6 October 2026.** In a mixed May session, House 3 (no panels, no battery) bought 2–2.5 times
its forecast need between 10 am and 3 pm. The surplus went back to the EB at ₹3.61, and the house ended
₹20.27 worse off than paying the EB alone. Its forecast was accurate: 16.3 units forecast, 16.0 used.
There were three causes.

1. **Stale price belief.** The agent's learned noon price, ₹3.61, came from earlier sessions in a
   neighbourhood where every home had surplus at noon. At that price over-buying looks free. The first
   hour of this session cleared at ₹7.45, and nothing corrected the belief.
2. **Unbounded quantile.** The critical ratio reached 1.0, which was turned into z = 3.7 standard
   deviations on a Gaussian tail, far past the P90 the forecaster is calibrated for.
3. **EB-backed hedge.** Whatever neighbours did not fill of the whole order, hedge included, the EB filled
   at retail. That can only lose money.

## Decision

Each agent is a LangGraph graph run per home per slot: perceive → project → value → order → speak
(`app/agents/household_agent.py`). The graph is deterministic, with no LLM in it
([ADR-0005](0005-llm-beside-the-critical-path.md)).

**Project.** Walk the battery through the rest of the session on the P50 forecast, net of contracts
already made. Before a power cut, hold back enough charge to ride through it, sized from the cautious view:
P90 load against P10 sun.

**Value.**

- Commitment quantile, from the expected price p̂:
  - seller: q = (p̂ − feed-in) / (retail − feed-in);
  - buyer: q = (retail − p̂) / (retail − feed-in);
  - during a power cut: 0.1 and 0.9, since a broken promise means lights out.
- **q is held to [0.1, 0.9].** The P10–P90 band is what conformal calibration covers
  ([ADR-0010](0010-hourly-forecasts-with-conformal-calibration.md)). Beyond it, a Gaussian tail is a
  guess.
- The spread σ comes from the P10–P90 widths of load and sun, treated as independent.
- **p̂ has two parts.** The first is the agent's learned price for that hour of day. Zero-Intelligence-Plus
  learning (Cliff, 1997) keeps it as an EMA with weight 0.3 and saves it across sessions. The second is a
  **within-session surprise**: how far the last hour that traded cleared above or below the agent's
  belief. The surprise carries into the next hour, fading by 0.8 each hour.

**Order.**

- A real surplus or shortfall becomes a **firm** order. `firm_kwh` is the expected quantity, which the EB
  stands behind. The newsvendor hedge on top is for neighbours only.
- Spare stored charge is offered **optionally**, never below the owner's reserve. Its floor is the higher
  of feed-in + ₹0.50 and 85% of p̂.
- Cheap neighbour energy is bought **optionally** to store for a later shortfall. The ceiling is the
  round-trip efficiency × the highest later retail tariff, less ₹0.50 for battery wear.
- Opening prices come from the agent's learned ZIP margin.

**Speak.** A template states what the agent is doing and why, using only the decision's own numbers. It is
the record of truth.

## Consequences

**Good**

- After the fix, the same session leaves every home better off than its EB-only bill. House 3 went from
  −₹20.27 to +₹20.83. From the second hour on, its price estimate tracks the market and its bids are
  within a few percent of its expected need.
- The worst case is bounded. No order exceeds the forecast's P90 need. A property test checks that the EB
  never fills more than the expected part of any order.
- Every number behind a decision is stored and explained, which serves objective O7.

**Bad / accepted**

- **Individual rationality (O6) holds per trade, not per session.** Every trade clears inside
  [feed-in, retail] by construction. A home's whole-session bill can still exceed its EB-only bill, when a
  hedge turns out not to be needed or the forecast misses. That is now an empirical result to measure
  across sessions, not a structural guarantee. `objectives.md` states it per tick and needs that
  distinction.
- The persistence 0.8, the [0.1, 0.9] bounds and the ₹0.50 wear cost are modelling choices, not fitted
  values.
- Net uncertainty is approximated as Gaussian from two independently forecast bands. Load and sun are not
  truly independent: a hot, clear day raises both.
- The first hour of a session still runs on the stale belief, since nothing has traded yet.
