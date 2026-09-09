# Runbook

Operational reference: starting the stack, checking it is healthy, and fixing the things that actually
go wrong.

## Start and stop

```bash
cp .env.example .env          # first time only
docker compose up -d          # core stack
docker compose ps             # status and health
docker compose logs -f backend
docker compose down           # stop, keep data
docker compose down -v        # stop and DESTROY the database
```

With Prometheus and Grafana (opt-in, to keep the default footprint small):

```bash
docker compose --profile observability up -d
```

| Service | URL |
|---|---|
| Dashboard | <http://localhost:5173> |
| API docs | <http://localhost:8000/docs> |
| Liveness | <http://localhost:8000/api/v1/health/live> |
| Readiness | <http://localhost:8000/api/v1/health/ready> |
| Metrics | <http://localhost:8000/metrics> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3001> (admin / `GRAFANA_PASSWORD`) |

## Health checks

**Liveness** answers "is the process alive?" and deliberately checks nothing external — a database blip
must not cause an orchestrator to kill healthy processes and turn a partial outage into a total one.

**Readiness** answers "should traffic reach this instance?", probes dependencies, and returns **503** when
any is down so a load balancer drains it.

```bash
curl -s http://localhost:8000/api/v1/health/ready | jq
```

## Quality gates

Exactly what CI runs:

```bash
docker compose exec backend ruff check app tests
docker compose exec backend ruff format --check app tests
docker compose exec backend mypy app
docker compose exec backend pytest

cd frontend && npm run lint && npm run format:check && npm run typecheck && npm run test:run && npm run build
```

## Database

```bash
docker compose exec postgres psql -U energy -d energy_transfer

# Confirm TimescaleDB loaded
\dx

# Backup / restore
docker compose exec -T postgres pg_dump -U energy energy_transfer > backup.sql
docker compose exec -T postgres psql -U energy -d energy_transfer < backup.sql
```

## LLM provider

Set `LLM_PROVIDER` in `.env`. Explanations degrade gracefully; trading never depends on this.

| Value | Requires |
|---|---|
| `stub` | nothing — deterministic, used by CI and tests |
| `groq` | `GROQ_API_KEY` from <https://console.groq.com/keys> (free tier) |
| `ollama` | Ollama installed **on the host**: `winget install Ollama.Ollama && ollama pull llama3.2:3b` |

Ollama is intentionally not a Compose service — see [Docker memory](#docker-runs-out-of-memory) below.

---

## Troubleshooting

### Docker runs out of memory

Docker Desktop's VM defaults to a fraction of host RAM; on this project's reference machine it is
**7.6 GiB of 15.8 GB**. Symptoms are containers killed with exit code 137, or Postgres refusing
connections under load.

- Raise it: Docker Desktop → Settings → Resources → Memory.
- Keep the `observability` profile off unless you need it.
- Never run an 8B model inside Compose. Use `LLM_PROVIDER=groq` (nothing local) or run Ollama on the
  host, where it reaches full host RAM and is addressed as `host.docker.internal:11434`.

### Backend restarts continuously

```bash
docker compose logs backend --tail=50
```

Most often a configuration validation failure at startup — which is intentional, since an invalid
deployment should fail loudly rather than misbehave during a market tick. Common causes:

| Message | Cause |
|---|---|
| `feed_in_tariff must be strictly less than retail_tariff` | Inverted tariff band; no price could satisfy objective O6. |
| `voltage_min_pu must be strictly less than voltage_max_pu` | Inverted statutory voltage band. |
| `GROQ_API_KEY is required` | `LLM_PROVIDER=groq` in production with no key. Use `stub`, or supply the key. |
| `DEBUG must be false in production` | `APP_ENV=production` with `DEBUG=true`. |

### Frontend cannot reach the API

Check `VITE_API_BASE_URL` in `.env`. It is read by the **browser**, not the container, so it must be
`http://localhost:8000/api/v1` — not `http://backend:8000`. Vite inlines `VITE_*` values at build time, so
changing one requires a rebuild:

```bash
docker compose up -d --build frontend
```

If the dashboard shows "API unreachable", confirm CORS: the browser's origin must appear in
`CORS_ORIGINS`.

### Hot reload not working

Bind-mounted files on Windows do not deliver inotify events into the Linux VM. Vite is already configured
with `usePolling: true` for this reason. If the backend stops reloading, confirm `./backend/app` is still
bind-mounted in `docker-compose.yml`.

### Port already in use

```bash
netstat -ano | findstr :8000     # Windows
```

Change the host-side port in `.env` (`API_PORT`, `POSTGRES_PORT`, `REDIS_PORT`).

### Tests pass locally but fail in CI

CI runs Python 3.12 on Linux; the reference dev machine has Python 3.14 on Windows. **Docker is the
source of truth** — run tests through `docker compose exec backend pytest` rather than a host
interpreter. Line endings are normalised by `.gitattributes`; if a diff shows every line changed, run
`git config core.autocrlf false` and re-clone.

### Rebuilding from scratch

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
```
