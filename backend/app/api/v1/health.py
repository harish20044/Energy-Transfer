"""Liveness and readiness probes.

These are separate on purpose. Liveness answers "is this process alive?" and
must never consult a dependency — otherwise a brief database blip causes the
orchestrator to kill healthy processes and turn a partial outage into a total
one. Readiness answers "should traffic be routed here?" and does probe
dependencies.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.config import Settings, get_settings
from app.schemas.health import (
    ComponentHealth,
    ComponentStatus,
    LivenessResponse,
    ReadinessResponse,
)

router = APIRouter(prefix="/health", tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/live", summary="Liveness probe")
async def live(settings: SettingsDep) -> LivenessResponse:
    """Report that the process is running. Checks nothing external."""
    return LivenessResponse(
        service=settings.app_name,
        version=settings.app_version,
    )


async def check_components(settings: Settings) -> list[ComponentHealth]:
    """Probe every dependency required to serve traffic.

    P0 has no external dependencies wired yet, so this reports only the
    application itself. Postgres and Redis probes are added in P1 with the
    persistence layer, and each appends its own :class:`ComponentHealth`.
    """
    _ = settings
    return [ComponentHealth(name="application", status=ComponentStatus.UP)]


@router.get("/ready", summary="Readiness probe")
async def ready(settings: SettingsDep, response: Response) -> ReadinessResponse:
    """Report whether this instance can serve traffic.

    Returns 503 when any required component is down, so that a load balancer
    drains this instance instead of sending it requests it cannot fulfil.
    """
    components = await check_components(settings)

    overall = (
        ComponentStatus.UP
        if all(component.status is ComponentStatus.UP for component in components)
        else ComponentStatus.DOWN
    )
    if overall is not ComponentStatus.UP:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status=overall,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
        components=components,
    )
