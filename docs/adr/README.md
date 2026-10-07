# Architecture Decision Records

Why the stack looks the way it does. Each record states the context, the decision, and the consequences
— including the ones we dislike.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-single-postgres-with-timescaledb.md) | One database: PostgreSQL + TimescaleDB (no MongoDB) | Accepted |
| [0003](0003-native-jwt-authentication.md) | Native JWT auth instead of Keycloak | Accepted |
| [0004](0004-lightgbm-over-deep-learning.md) | LightGBM quantile models over TensorFlow/LSTM | Accepted |
| [0005](0005-llm-beside-the-critical-path.md) | The LLM sits beside the trading path, never inside it | Accepted |
| [0006](0006-pure-domain-layer.md) | The domain layer performs no I/O | Accepted |
| [0007](0007-calibrated-synthetic-chennai-data.md) | Synthetic Chennai data, calibrated to published measurements and checked in CI | Accepted |
| [0008](0008-planning-sessions-with-the-eb-as-provider.md) | Planning sessions with the EB as provider, instead of a free-running market clock | Accepted |
| [0009](0009-newsvendor-agents-in-the-calibrated-band.md) | Agents commit as newsvendors, inside the forecast's calibrated band | Accepted |
| [0010](0010-hourly-forecasts-with-conformal-calibration.md) | Hourly forecasts 1–24 hours ahead, with conformally calibrated quantiles (refines 0004) | Accepted |
| [0011](0011-groq-advisor-as-a-tool-loop.md) | The household advisor: a tool-using LLM on Groq, beside the trading path (refines 0005) | Accepted |
| [0012](0012-measuring-the-objectives.md) | Measuring the objectives: an in-memory harness, a hindsight optimum and an AC check | Accepted |
| [0013](0013-one-graph-run-per-slot.md) | One decision-graph run per slot for every agent (refines 0009) | Accepted |

Records 0002–0005 each supersede or refine a row of the Zeroth Review tech stack. They exist so that the
departures can be defended with the trade-off that was actually weighed, rather than recalled from memory.

ADRs are immutable once accepted. A reversal gets a new record superseding the old one; the original stays
so the reasoning history remains readable.
