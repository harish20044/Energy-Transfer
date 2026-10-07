# 13. One decision-graph run per slot for every agent

- **Status:** Accepted
- **Date:** 2026-10-07
- **Refines:** [ADR-0009](0009-newsvendor-agents-in-the-calibrated-band.md)

## Context

ADR-0009 ran each household's LangGraph decision graph once per slot. Measuring objective O3 showed what
that costs. Each run spent about 15–17 ms in LangGraph's own machinery (building tasks, channels, retries),
against well under 1 ms in the agent's actual steps. One slot took about 170 ms at 10 homes and 3–4 s at
100, against a target of p95 < 200 ms at 100 homes.

The grid safety layer had a smaller version of the same problem. It recomputed the feeder's subtrees and
paths from scratch on every check, which grows with the cube of the feeder's size: about 0.9 s per slot at
100 homes.

## Decision

- **One graph run per slot takes every agent through the same five steps** (perceive → project → value →
  order → speak, `decide_slots`).
  - Each step is applied to each agent separately, and an agent only ever sees its own observation.
  - Decisions are identical to running the graph per household, and the tests are unchanged.
  - `decide_slot` still decides for one household, through the same graph.
- **The feeder's topology is worked out once per feeder** and cached (`app/domain/grid/network.py`). A
  feeder is an immutable value, so its subtrees and paths never change. Malformed trees still fail where
  they always did.

## Consequences

- Clearing a slot dropped to about 5 ms at 10 homes and about 70–180 ms at 100 homes. The exact figures are
  in [evaluation.md](../evaluation.md).
- The agent is still a LangGraph state machine. The graph now carries the whole population through each
  step, rather than one household through all of them.
- If agents ever needed different graphs, or tools with I/O, the batch would have to split by graph.
  Today every household runs the same deterministic steps.
