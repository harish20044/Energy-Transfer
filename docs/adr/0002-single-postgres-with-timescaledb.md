# 2. One database: PostgreSQL with TimescaleDB

- **Status:** Accepted
- **Date:** 2026-09-09
- **Supersedes:** the "MongoDB + PostgreSQL" row of the Zeroth Review stack

## Context

The reviewed stack listed **MongoDB** for agent state and logs alongside **PostgreSQL** for the
settlement ledger. The implied split was document-shaped data in Mongo, money in Postgres.

Three facts undermine it:

1. **The data is not document-shaped.** The heavy tables — meter readings, forecasts, clearing prices,
   agent decisions — are append-only *time-series* keyed by `(entity, timestamp)`. That is the shape
   TimescaleDB hypertables exist for, with automatic partitioning, compression and continuous
   aggregates. Mongo has no comparable answer, and PostgreSQL `JSONB` already covers the genuinely
   schemaless fields (agent scratch state, LLM rationale payloads) with GIN indexing.
2. **Settlement spans both stores.** A trade updates balances *and* agent state. Split across two
   databases there is no transaction boundary, so the system needs either a distributed-transaction
   protocol or an idempotent-retry reconciliation path — significant complexity for a benefit that was
   never identified.
3. **Two databases cost double.** Two connection pools, two backup and restore procedures, two failure
   modes, two sets of migrations, two containers in an environment where Docker Desktop's VM has only
   7.6 GiB in total.

## Decision

Use **PostgreSQL 16 with the TimescaleDB extension** as the single source of truth.

- Time-series (meter readings, forecasts, prices, tick records) → hypertables
- Semi-structured agent state and LLM output → `JSONB` columns
- Ledger, balances and identity → ordinary relational tables under full ACID guarantees

## Consequences

**Good**

- Settlement is one ACID transaction. Money and agent state cannot diverge.
- One migration tool (Alembic), one backup story, one thing to operate.
- Continuous aggregates make the dashboard's rollups cheap.
- Comfortably inside free tiers — Neon and Supabase both offer managed Postgres free.

**Bad / accepted**

- Deep schema changes are heavier than in a schemaless store. Mitigated by keeping genuinely fluid
  fields in `JSONB` and versioning those payloads.
- TimescaleDB is an extension, so the base image is `timescale/timescaledb` rather than stock
  `postgres`. Managed providers without the extension would need hypertables replaced by native
  declarative partitioning — a contained change, isolated to the migration layer.
