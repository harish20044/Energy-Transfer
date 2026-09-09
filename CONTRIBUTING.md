# Contributing

## Setup

Docker Desktop is the only prerequisite.

```bash
cp .env.example .env
docker compose up -d
```

Docker is the **source of truth for the development environment**. The reference machine runs Python
3.14 on Windows while the project targets 3.12 on Linux, so running tests against a host interpreter can
disagree with CI. Run them in the container.

## Quality gates

CI runs exactly these. Run them before pushing.

```bash
# Backend
docker compose exec backend ruff check app tests
docker compose exec backend ruff format --check app tests
docker compose exec backend mypy app            # strict
docker compose exec backend pytest              # 80% coverage floor

# Frontend
cd frontend
npm run lint && npm run format:check && npm run typecheck && npm run test:run && npm run build
```

With `make` available, `make ci` runs all of it.

## Conventions

**Commits** follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `ci:`, `perf:`.

**Branches:** `feat/short-description`, `fix/short-description`.

**The domain layer is pure.** Nothing under `backend/app/domain/` may touch a database, network, clock,
filesystem or global random source. That constraint is what makes the market invariants property-testable
— see [ADR-0006](docs/adr/0006-pure-domain-layer.md).

**Invariants get property tests.** Anything claimed absolutely — zero grid violations, no participant
worse off — is verified with Hypothesis over generated inputs, not with a handful of examples.

**Architecturally significant decisions get an ADR.** Copy the format of an existing file in
[`docs/adr/`](docs/adr/) and number it sequentially. Include the consequences you dislike; an ADR that
lists only benefits is not recording a trade-off.

## Testing layout

| Directory | Contains | Needs |
|---|---|---|
| `tests/unit/` | Pure, fast, no I/O | nothing |
| `tests/property/` | Hypothesis invariant tests | nothing |
| `tests/integration/` | Repository and service tests | Postgres, Redis |
| `tests/e2e/` | Full stack through the API | the whole stack |

Mark slow tests with `@pytest.mark.slow` so the default run stays fast.

## Security

Never commit `.env`, API keys or real personal data. CodeQL and Trivy run on every pull request. Report a
vulnerability privately to the maintainer rather than opening a public issue.
