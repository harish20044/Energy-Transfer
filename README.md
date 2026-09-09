# Energy-Transfer

**Agentic AI-based peer-to-peer energy trading in microgrids.**

[![CI](https://github.com/harish20044/Energy-Transfer/actions/workflows/ci.yml/badge.svg)](https://github.com/harish20044/Energy-Transfer/actions/workflows/ci.yml)
[![CodeQL](https://github.com/harish20044/Energy-Transfer/actions/workflows/codeql.yml/badge.svg)](https://github.com/harish20044/Energy-Transfer/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5.7-blue.svg)](https://www.typescriptlang.org/)

> M.Tech Industry Accelerate Program · VIT Chennai · Harish P

---

## The problem

A **microgrid** is a local cluster of homes on one distribution feeder. Some have rooftop solar and a
battery (**prosumers**); some only consume (**consumers**).

At 1pm today, prosumer House A exports surplus solar to the utility at a **feed-in tariff** of ~₹3/kWh.
At that same moment, neighbour House B buys from the utility at a **retail tariff** of ~₹8/kWh. The
electricity travels a few hundred metres — but ₹5/kWh of value is lost to that spread. Worse, when solar
penetration is high the feeder cannot absorb all the surplus, and it is **curtailed: wasted outright**.

## What this builds

A **local energy market** where A sells directly to B at a price between ₹3 and ₹8, leaving both strictly
better off than dealing with the utility — with AI agents making the decisions and a safety layer
guaranteeing the physical grid can actually carry the resulting power flows.

### The agents

| Agent | Count | Responsibility |
|---|---|---|
| **Prosumer / Consumer** | one per household | Forecasts its own load and solar, plans its battery, sets a reservation price, submits a bid or ask |
| **Market Operator** | 1 | Collects orders each interval, clears a double auction, produces the clearing price and matched trades |
| **Grid Safety** | 1 | Runs power flow over the proposed trades and **holds veto power** — curtails until physically feasible |
| **Settlement** | 1 | Writes final trades to an append-only hash-chained ledger and moves energy and money balances |

### One market tick — every 15 simulated minutes

1. **Forecast** — each agent predicts its next-interval load and PV as **P10/P50/P90**, a range rather than a point.
2. **Position** — computes net surplus or deficit, plans battery charge/discharge, derives a reservation price.
3. **Bid** — submits `(side, quantity_kWh, limit_price)`; the gate closes.
4. **Clear** — asks sorted ascending, bids descending, intersection found → one **uniform clearing price**, bounded to `[feed_in_tariff, retail_tariff]`.
5. **Safety** — linearized DistFlow over the IEEE 33-bus feeder checks thermal, transformer and voltage limits. A violation curtails marginal trades and re-checks.
6. **Settle** — final trades are hashed into the ledger; balances update.
7. **Explain** — an LLM writes a plain-English rationale per household; everything streams to the dashboard over WebSocket.

> *"You sold 2.1 kWh at ₹5.40 because your battery was already at 85% and this evening's demand is forecast low."*

### What "agentic" means here — honestly

The **decisions are deterministic and auditable** (optimization plus explicit rules), because money moves
and grid safety is at stake. The **agents are genuinely autonomous** — LangGraph state machines owning
their own strategy, battery policy and risk posture. The **LLM sits beside the critical path, not inside
it**, handling what it is actually good at: explaining decisions, interpreting natural-language
preferences ("keep 40% charge for the evening"), and triaging anomalies.

Money must not move through a non-deterministic, unauditable, multi-second component.
*LLM in the loop, not in the critical path.*

---

## Objectives

Success is not "it runs" — it is these seven numbers, measured against honest baselines and reproducible
from a single command.

| # | Objective | Metric | Target |
|---|---|---|---|
| **O1** | Accurate short-term forecasting | nMAE + pinball loss vs. seasonal-naive | ≥25% nMAE reduction |
| **O2** | Efficient P2P matching | Allocative efficiency vs. offline LP optimum | ≥95% |
| **O3** | Autonomous trading | Ticks cleared unattended; decision latency | 100%; p95 <200 ms @ 100 agents |
| **O4** | Safe energy allocation | Constraint violations after the safety layer | **exactly 0** |
| **O5** | Renewable utilisation | Self-sufficiency ratio ↑; grid export ↓ | export ↓ ≥30% |
| **O6** | Economic benefit | Mean bill vs. grid-only; individual rationality | ↓10–20%; nobody worse off |
| **O7** | Explainability | Trades carrying machine-readable + NL rationale | 100% |

**O4** and **O6** are provable invariants, not merely measurements — both are enforced by property-based
tests. See [`docs/objectives.md`](docs/objectives.md) for how each is computed.

---

## Quick start

Requires Docker Desktop. Nothing else needs installing.

```bash
git clone https://github.com/harish20044/Energy-Transfer.git
cd Energy-Transfer
cp .env.example .env
docker compose up -d
```

| Service | URL |
|---|---|
| Dashboard | <http://localhost:5173> |
| API docs | <http://localhost:8000/docs> |
| Readiness | <http://localhost:8000/api/v1/health/ready> |
| Metrics | <http://localhost:8000/metrics> |

Add Prometheus and Grafana with `docker compose --profile observability up -d` (opt-in, to keep the
default memory footprint small).

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2 (async) · Alembic |
| Database | PostgreSQL 16 + **TimescaleDB** (hypertables for meter/forecast series) |
| Cache & realtime | Redis 7 (WebSocket fan-out, tick scheduling, rate limiting) |
| Forecasting | **LightGBM** quantile models · seasonal-naive baseline · PyTorch LSTM (offline benchmark) |
| Grid physics | **pandapower** · IEEE 33-bus feeder · linearized DistFlow in the hot path |
| Agents | **LangGraph** state machines |
| LLM | **Groq** (default) · Ollama (offline) · stub (CI) — one interface, swapped by env var |
| Frontend | React 19 · TypeScript · Vite · Tailwind v4 · Recharts · TanStack Query |
| Quality | Ruff · mypy --strict · pytest + Hypothesis · ESLint · Prettier · Vitest |
| CI/CD | GitHub Actions · GHCR · Dependabot · CodeQL · Trivy |

Every component is free and open source. The only hosted service is Groq, on its free tier — and the
`stub` provider means CI never needs a key or a network call.

Four deliberate departures from the original proposal — dropping MongoDB and Keycloak, choosing LightGBM
over TensorFlow/LSTM, and moving the LLM out of the trading path — are each recorded with their reasoning
in [`docs/adr/`](docs/adr/).

---

## Layout

```
backend/
  app/
    core/          config, logging, middleware, db, redis
    api/v1/        HTTP + WebSocket routes
    schemas/       Pydantic wire contracts
    domain/        ← PURE, ZERO I/O: market, grid, battery, ledger
    forecasting/   features, models, backtest harness
    agents/        LangGraph graphs, LLM provider interface
    simulator/     synthetic households and scenarios
  tests/           unit · property · integration · e2e
frontend/
  src/             components, hooks, api, store, types
infra/             postgres init, prometheus, grafana
docs/              architecture, objectives, runbook, ADRs
```

**The most important structural rule:** `app/domain/` performs no database, network, clock or file access.
The auction, grid constraint check, battery model and ledger are deterministic functions. That is what
makes the market invariants property-testable, lets the same engine run inside the offline benchmark
harness, and keeps the research contribution independent of the web framework.

---

## Development

```bash
# Backend gates — exactly what CI runs
docker compose exec backend ruff check app tests
docker compose exec backend ruff format --check app tests
docker compose exec backend mypy app
docker compose exec backend pytest

# Frontend gates
cd frontend
npm run lint && npm run format:check && npm run typecheck && npm run test:run && npm run build
```

`mypy` runs strict, `pytest` enforces an 80% coverage floor, and Vitest enforces 80% lines / 75% branches.
With `make` installed, `make ci` runs all of it in one command.

---

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **P0** | Repo, Docker Compose, CI/CD, quality gates, docs | ✅ done |
| **P1** | Thin vertical slice: simulator → forecast → auction → grid check → ledger → API → dashboard | next |
| **P2** | Auction variants, IEEE 33-bus DistFlow, battery degradation, property tests | |
| **P3** | Ausgrid ingestion, LightGBM quantile models, backtest harness, benchmark table | |
| **P4** | LangGraph agents, risk-aware bidding, LLM rationale + NL preferences | |
| **P5** | Auth + RBAC, full dashboard, scenario controls, Grafana | |
| **P6** | Evaluation suite generating the objectives table, load test, deployment | |

## Documentation

- [Architecture](docs/architecture.md) — components, data flow, the market tick in detail
- [Objectives](docs/objectives.md) — how each of O1–O7 is measured
- [Runbook](docs/runbook.md) — operating, troubleshooting, common tasks
- [ADRs](docs/adr/) — why the stack looks the way it does

## Data

- **Ausgrid Solar Home Electricity Data** — 300 real homes, half-hourly, 3 years (free, public)
- **Synthetic simulator** — seeded and reproducible, scales agent count, constructs stress scenarios

## License

[MIT](LICENSE)
