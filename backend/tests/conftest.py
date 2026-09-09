"""Shared test fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import AppEnv, LogFormat, Settings, get_settings
from app.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Deterministic settings, independent of the ambient environment.

    Values are passed explicitly because init keyword arguments outrank both
    environment variables and any ``.env`` file in pydantic-settings' source
    precedence, which keeps these tests identical on a laptop and in CI.
    """
    return Settings(
        app_env=AppEnv.DEVELOPMENT,
        app_name="energy-transfer-test",
        app_version="0.1.0-test",
        debug=True,
        log_format=LogFormat.CONSOLE,
        # Deliberately messy: whitespace and a trailing empty entry, so the
        # parsing in `cors_origin_list` is genuinely exercised.
        cors_origins="http://localhost:5173, http://localhost:3000 ,",
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """An application instance wired to the test settings.

    ``create_app`` receives the settings for CORS and routing, but endpoints
    resolve configuration through the ``get_settings`` dependency, so that is
    overridden too — otherwise routes would read the process-wide singleton.
    """
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """An HTTP client speaking directly to the ASGI app, with no network."""
    # raise_app_exceptions=False lets tests observe the 500 response produced by
    # the unhandled-exception handler instead of the exception escaping.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
