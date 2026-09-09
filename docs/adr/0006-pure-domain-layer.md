# 6. The domain layer performs no I/O

- **Status:** Accepted
- **Date:** 2026-09-09

## Context

The market engine, grid constraint check, battery model and settlement ledger are the research
contribution of this project. They also carry its two hardest guarantees:

- **O4** — zero grid constraint violations after the safety layer
- **O6** — no participant ends up worse off than not trading (individual rationality)

Claims like these cannot be established by a handful of example-based tests. They need
**property-based testing**: thousands of generated scenarios asserting an invariant holds in all of them.
That is only possible if the code under test is deterministic and free of I/O — a function that opens a
database connection or reads the clock cannot be run ten thousand times in a Hypothesis loop.

The same code must also run inside an **offline benchmark harness** that replays historical Ausgrid data
at high speed to produce the evaluation table, entirely outside the web application.

## Decision

`backend/app/domain/` contains **pure functions and immutable data only**. Specifically, no module under
`domain/` may:

- import SQLAlchemy, Redis, `httpx`, or any FastAPI symbol
- read the wall clock (`datetime.now`, `time.time`) — timestamps arrive as arguments
- read the environment, the filesystem or a network socket
- generate randomness from an implicit global source — seeds are passed in
- log through a globally configured logger

Everything the domain needs is passed in; everything it produces is returned. Persistence, scheduling and
transport live in `services/`, `workers/` and `api/`, which depend on `domain/` and never the reverse.

## Consequences

**Good**

- O4 and O6 become machine-checked properties over generated inputs rather than assertions in prose.
  "No participant is ever worse off than not trading, verified across thousands of random microgrid
  configurations" is a genuinely strong result.
- The market engine runs unchanged in the API, in the benchmark harness and in tests.
- Domain tests need no database, no fixtures and no container; the whole suite runs in seconds.
- The contribution stays independent of FastAPI, so the framework could change without touching it.

**Bad / accepted**

- More plumbing: callers must assemble inputs and persist outputs explicitly, rather than letting a
  domain object fetch what it needs.
- Some duplication between domain dataclasses and the SQLAlchemy models that persist them. Accepted
  deliberately — coupling the two would drag the ORM into the pure layer and forfeit everything above.

## Enforcement

Ruff's banned-API rules reject the forbidden imports inside `domain/`, so a violation fails CI rather
than relying on reviewer vigilance.
