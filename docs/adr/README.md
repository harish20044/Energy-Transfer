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

Records 0002–0005 each supersede or refine a row of the Zeroth Review tech stack. They exist so that the
departures can be defended with the trade-off that was actually weighed, rather than recalled from memory.

ADRs are immutable once accepted. A reversal gets a new record superseding the old one; the original stays
so the reasoning history remains readable.
