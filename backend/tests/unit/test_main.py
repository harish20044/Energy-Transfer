"""Application wiring: metadata, metrics, middleware and error handling."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import AppEnv, LLMProvider, LogFormat, Settings
from app.core.middleware import REQUEST_ID_HEADER
from app.main import create_app, lifespan

pytestmark = pytest.mark.unit


async def test_root_returns_service_metadata(client: AsyncClient, settings: Settings) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == settings.app_name
    assert body["version"] == settings.app_version
    assert body["docs"] == "/docs"
    assert body["health"] == "/api/v1/health/ready"


async def test_metrics_endpoint_serves_prometheus_text(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "python_info" in response.text


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert REQUEST_ID_HEADER in response.headers
    assert len(response.headers[REQUEST_ID_HEADER]) > 0


async def test_upstream_request_id_is_preserved(client: AsyncClient) -> None:
    """An id set by a proxy must survive, so a trace spans the whole hop chain."""
    incoming = "11111111-2222-3333-4444-555555555555"

    response = await client.get(
        "/api/v1/health/live",
        headers={REQUEST_ID_HEADER: incoming},
    )

    assert response.headers[REQUEST_ID_HEADER] == incoming


async def test_unhandled_exception_returns_a_sanitised_500(settings: Settings) -> None:
    """Internal failures must not leak exception text to the caller."""
    app = create_app(settings)

    @app.get("/boom")
    async def boom() -> None:
        msg = "database credentials rejected for user 'energy'"
        raise RuntimeError(msg)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as probe:
        response = await probe.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "credentials" not in response.text


async def test_docs_are_disabled_in_production() -> None:
    """Interactive docs describe the full attack surface; withhold them in prod."""
    production = Settings(
        app_env=AppEnv.PRODUCTION,
        debug=False,
        llm_provider=LLMProvider.STUB,
        log_format=LogFormat.JSON,
    )
    app = create_app(production)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as probe:
        docs = await probe.get("/docs")
        openapi = await probe.get("/openapi.json")

    assert docs.status_code == 404
    assert openapi.status_code == 404


async def test_cors_headers_are_returned_for_an_allowed_origin(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/health/live",
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_lifespan_runs_cleanly(app: FastAPI) -> None:
    """Startup and shutdown must complete without raising."""
    async with lifespan(app):
        pass
