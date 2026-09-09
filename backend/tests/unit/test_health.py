"""Liveness and readiness probe behaviour."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1 import health
from app.core.config import Settings
from app.schemas.health import ComponentHealth, ComponentStatus

pytestmark = pytest.mark.unit


async def test_live_returns_up(client: AsyncClient, settings: Settings) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ComponentStatus.UP
    assert body["service"] == settings.app_name
    assert body["version"] == settings.app_version


async def test_ready_returns_up_with_components(client: AsyncClient, settings: Settings) -> None:
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == ComponentStatus.UP
    assert body["environment"] == settings.app_env.value
    assert [component["name"] for component in body["components"]] == ["application"]


async def test_ready_returns_503_when_a_component_is_down(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing dependency must drain this instance, not silently serve errors."""

    async def failing_components(_settings: Settings) -> list[ComponentHealth]:
        return [
            ComponentHealth(name="application", status=ComponentStatus.UP),
            ComponentHealth(
                name="postgres",
                status=ComponentStatus.DOWN,
                detail="connection refused",
                latency_ms=12.5,
            ),
        ]

    monkeypatch.setattr(health, "check_components", failing_components)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as probe:
        response = await probe.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == ComponentStatus.DOWN

    postgres = next(c for c in body["components"] if c["name"] == "postgres")
    assert postgres["detail"] == "connection refused"
    assert postgres["latency_ms"] == 12.5


async def test_check_components_reports_the_application(settings: Settings) -> None:
    components = await health.check_components(settings)

    assert len(components) == 1
    assert components[0].name == "application"
    assert components[0].status is ComponentStatus.UP
