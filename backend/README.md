# Energy-Transfer — backend

FastAPI service hosting the market engine, agent runtime, forecasting models and
settlement ledger. See [`../docs/architecture.md`](../docs/architecture.md) for
how the pieces fit together.

## Layout

| Path | Responsibility |
|---|---|
| `app/core/` | Configuration, logging, middleware, database and Redis clients |
| `app/api/v1/` | HTTP and WebSocket routes |
| `app/schemas/` | Pydantic wire contracts |
| `app/domain/` | **Pure** market, grid, battery and ledger logic — no I/O |
| `app/forecasting/` | Feature pipeline, models, backtest harness |
| `app/agents/` | LangGraph agent graphs and the LLM provider interface |
| `app/simulator/` | Synthetic household generation and scenarios |
| `tests/` | `unit/`, `property/`, `integration/`, `e2e/` |

`app/domain/` is deliberately free of database, network and clock access. The
auction, grid constraint check, battery model and ledger are deterministic
functions, which is what makes the market invariants property-testable and lets
the same engine run inside the offline benchmark harness.

## Running

Everything runs through Docker Compose from the repository root:

```bash
docker compose up -d
```

- API docs — <http://localhost:8000/docs>
- Liveness — <http://localhost:8000/api/v1/health/live>
- Readiness — <http://localhost:8000/api/v1/health/ready>
- Metrics — <http://localhost:8000/metrics>

## Quality gates

```bash
docker compose exec backend ruff check app tests
docker compose exec backend ruff format --check app tests
docker compose exec backend mypy app
docker compose exec backend pytest
```

`mypy` runs in strict mode and `pytest` enforces an 80% coverage floor; CI runs
exactly these four commands.

## Dependency groups

Base install is the API skeleton only. Later phases install what they need:

```bash
pip install -e ".[dev]"      # tooling and tests
pip install -e ".[db]"       # SQLAlchemy, asyncpg, Alembic, Redis   (P1)
pip install -e ".[grid]"     # pandapower, NumPy                     (P2)
pip install -e ".[ml]"       # LightGBM, pandas, scikit-learn        (P3)
pip install -e ".[agents]"   # LangGraph, Groq                       (P4)
pip install -e ".[auth]"     # PyJWT, argon2                         (P5)
```
