# syntax=docker/dockerfile:1.7
#
# Multi-stage build.
#   development — editable install with dev tooling, hot reload, root ok
#   production  — runtime deps only, non-root, no build toolchain in the image
#
# Python is pinned to 3.12 rather than latest: it has the widest wheel coverage
# for the scientific stack (LightGBM, pandapower, asyncpg) that later phases add.

# =============================================================================
FROM python:3.12-slim AS base
# =============================================================================

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

# curl is used by the container healthcheck; libpq is needed by asyncpg (P1).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
FROM base AS development
# =============================================================================

# Dependency metadata is copied on its own, and the package is stubbed out, so
# that editing source does not invalidate the (slow) dependency install layer.
COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install -e ".[dev]"

COPY app ./app
COPY tests ./tests

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
FROM base AS production
# =============================================================================

# Run as an unprivileged user: a container escape should not land on root.
RUN groupadd --system --gid 1001 energy \
    && useradd --system --uid 1001 --gid energy --create-home energy

COPY pyproject.toml README.md ./
RUN mkdir -p app && touch app/__init__.py \
    && pip install --no-cache-dir "."

COPY --chown=energy:energy app ./app

USER energy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1

# No --reload, and worker count is set by the platform via WEB_CONCURRENCY.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
