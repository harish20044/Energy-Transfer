"""Wire contracts for the health endpoints."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ComponentStatus(StrEnum):
    """Health of a single dependency."""

    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class ComponentHealth(BaseModel):
    """Health of one dependency the service needs in order to do its job."""

    name: str = Field(description="Dependency name, e.g. 'postgres'.")
    status: ComponentStatus
    detail: str | None = Field(
        default=None,
        description="Human-readable context, present when not 'up'.",
    )
    latency_ms: float | None = Field(
        default=None,
        ge=0,
        description="Round-trip time of the probe, when one was performed.",
    )


class LivenessResponse(BaseModel):
    """Answer to 'is the process alive?'.

    Deliberately checks nothing external: a failing database must not cause an
    orchestrator to kill an otherwise healthy process.
    """

    status: ComponentStatus = ComponentStatus.UP
    service: str
    version: str


class ReadinessResponse(BaseModel):
    """Answer to 'can this instance serve traffic?'.

    Unlike liveness, this does probe dependencies, and returns 503 when any
    required component is down.
    """

    status: ComponentStatus
    service: str
    version: str
    environment: str
    components: list[ComponentHealth] = Field(default_factory=list)
