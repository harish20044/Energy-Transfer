-- Runs once, on first initialisation of an empty Postgres data directory.
-- Schema itself is owned by Alembic migrations — this file only installs the
-- extensions those migrations depend on.

-- Hypertables for meter readings, forecasts and clearing prices: all of this
-- project's heaviest tables are append-only time-series.
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- gen_random_uuid() for primary keys.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Trigram indexes for household / operator search.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
