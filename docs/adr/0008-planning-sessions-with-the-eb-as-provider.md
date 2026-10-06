# 8. Planning sessions with the EB as provider, instead of a free-running market clock

- **Status:** Accepted
- **Date:** 2026-10-06
- **Supersedes:** the tick worker and "The market tick" section of the original architecture

## Context

The first working market ran on a background clock. A tick cleared every 15 simulated minutes, and
pressing Play ran a whole day in about two and a half minutes. Two problems followed.

1. **It did not behave like a market a household could take part in.** The clock ran on its own, the day
   always started at midnight, and nobody chose the conditions. The user's review: the dashboard "keeps
   on running... in reality it will not happen". They wanted to pick a start time, set the scenario and
   what-ifs, see each home's predicted need or spare energy, and then watch the agents trade it.
2. **It traded almost nothing.** Clearing each 15-minute interval as it happened, with similar homes,
   meant every home had surplus at the same moment and none had need. One trade a day was typical. The
   utility, the EB, was outside the market: the price band used its tariffs, but nobody could buy from it.

## Decision

Replace the clock with a **planning session** that the user starts. Forward positions are fixed for every
hour first, then delivered, as in an ahead market.

**Set up.** The user picks a date, a start hour, a horizon of 4, 8, 12 or 24 hours, and a weather scenario.
What-ifs are optional.

- Per home: guests, a family away window, work from home, dusty or shaded panels up to none at all, and
  battery size and starting charge.
- For the feeder: an EB power cut window, changed tariffs, and an evening peak surcharge (6–10 pm).

**Plan** (`app/engine/session.py:plan_session`). Each home is forecast for the whole horizon. Then each
hourly slot is cleared in time order.

1. Every home's agent decides what to offer or ask for
   ([ADR-0009](0009-newsvendor-agents-in-the-calibrated-band.md)).
2. Neighbours negotiate in rounds inside the band from feed-in (₹3.61, TNERC Order 8/2021) to retail
   (₹10.50, the TN 801–1000 units slab). Grid safety then curtails what the feeder cannot carry.
3. **The EB stands behind every firm order.** It sells a buyer's unmatched expected need at retail and
   buys a seller's unmatched expected surplus at feed-in, so every home always gets its electricity.
   Neighbours are the cheaper option when they have some to spare.
   - Optional orders, such as selling spare stored charge or buying to store, never fall back to the EB.
   - Nor does a firm order's hedge, the margin above expected need: the EB already supplies any real
     shortfall in real time, at the same tariff.
4. During an EB power cut there is no fallback. Unmatched need is unserved, and unmatched surplus is
   stranded.

Offers, trades, hash-chained ledger entries, curtailments, positions and every agent decision are
persisted.

**Play.** "Next hour" delivers the next slot as four 15-minute intervals, against what the simulated
weather and family actually do (`app/domain/settlement/delivery.py`).

- Neighbour contracts are honoured on the wire. The battery absorbs the forecast error first, and the
  EB settles the rest at its tariffs.
- During a power cut, energy the battery cannot cover is unserved, and surplus it cannot store is
  curtailed.
- "Run to end" steps hour by hour with a short pause, and always stops at the horizon.

**Money.** Each home sees separate amounts:

- earned from neighbours;
- paid to neighbours;
- paid to the EB;
- earned from the EB;
- what the same hours would have cost with the EB alone.

There is no signed net balance.

**Removed:** the background runner, play, pause and speed, the `running` and `seconds_per_tick` columns
(migration `c7d2f84a1e93`), the per-tick engine and its battery policy.

## Consequences

**Good**

- The forecast has a job: agents commit hours ahead, so forecast quality now changes what households pay.
- Mixed neighbourhoods trade realistically. In a May session where three homes have no panels and three
  have large batteries, 50 units moved between neighbours over 12 hours, and every home beat its EB-only
  bill.
- The demo is controllable. A panel member can set conditions, step one hour, inspect a slot's
  negotiation, and see the EB's part.
- Power cuts, tariff changes and family changes are first-class inputs, not separate code paths.

**Bad / accepted**

- One feeder, one session. Whoever plans replaces the session for every user. That fits a demo, not a
  multi-tenant service.
- Planning is synchronous: 2–5 s for a 12-hour session in Docker. A 24-hour plan takes longer.
- Slots are hourly while delivery settles every 15 minutes. Within-hour swings are left to the battery and
  the EB.
- Objective O3's latency target was written per 15-minute tick. Its closest equivalent is now the time to
  clear one slot, which has not been measured yet.
