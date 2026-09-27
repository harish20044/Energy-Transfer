"""Async SQLAlchemy engine, session factory, and the declarative base.

One engine per process, created lazily so importing this module never opens a
connection — tests and the CLI both need to import models without a database
available.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base every ORM model inherits from."""


@lru_cache(maxsize=1)
def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the process-wide async engine, created on first use."""
    settings = settings or get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        # Keep the pool small: this is a demo-scale microgrid, not a fleet of
        # API replicas. A stuck connection under load is a bug to find, not
        # something to paper over with a huge pool.
        pool_size=5,
        max_overflow=5,
        echo=settings.debug and settings.app_env.value == "development",
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one request-scoped session.

    Commits on clean exit, rolls back on any exception, always closes — a
    request must never leave a connection dangling in the pool.
    """
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
