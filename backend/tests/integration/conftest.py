"""Fixtures for tests that need a real database connection.

Runs against whatever `DATABASE_URL` the environment points at — the
docker-compose Postgres locally, the `postgres` service container in CI —
rather than a mocked session, because the thing worth proving here is that
the ORM, the migration, and the actual driver agree with each other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine, get_sessionmaker
from app.main import create_app


@pytest.fixture(autouse=True)
async def _fresh_engine_per_test() -> AsyncIterator[None]:
    """Dispose the cached engine after every test.

    `get_engine`/`get_sessionmaker` are process-wide `lru_cache`d singletons —
    correct for the running app, which has exactly one event loop for its
    whole life. Tests don't: pytest-asyncio's default fixture loop scope is
    "function", so each test runs on its own fresh loop. Without this, the
    engine created by test 1 stays cached with connections bound to test 1's
    (now-closed) loop, and test 2 fails with "Future attached to a different
    loop" the moment it touches the database.
    """
    yield
    await get_engine().dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session bound to the real, migrated database.

    Rolled back rather than committed, so a test's writes never outlive it —
    this is what lets tests run repeatedly without colliding on unique
    constraints like the email index.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def integration_app() -> FastAPI:
    """The real app, wired to the real database — no dependency overrides.

    Distinct from the `app` fixture in the top-level conftest, which overrides
    `get_settings` for isolated unit tests; these tests want the production
    wiring intact.
    """
    return create_app()


@pytest.fixture
async def api_client(integration_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client that drives the real app end to end, including its own
    request-scoped database sessions — which is what actually proves the
    commit-on-success path in `get_db` works, not just the ORM in isolation."""
    transport = ASGITransport(app=integration_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
