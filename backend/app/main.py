"""FastAPI application factory and ASGI entrypoint.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware

log = get_logger(__name__)

DESCRIPTION = """
Agentic AI-based peer-to-peer energy trading in microgrids.

Households with rooftop solar and batteries trade surplus electricity directly
with their neighbours through a double auction, at prices strictly between the
feed-in tariff and the retail tariff — so both sides beat the utility. A grid
safety layer holds veto power over every proposed allocation.
"""


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Log the resolved operating configuration on startup and shutdown."""
    settings = get_settings()
    log.info(
        "service.startup",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
        llm_provider=settings.llm_provider.value,
        auction_mechanism=settings.auction_mechanism.value,
        tick_minutes=settings.market_tick_minutes,
        tariff_band=f"{settings.feed_in_tariff}-{settings.retail_tariff} {settings.currency}",
    )
    yield
    log.info("service.shutdown", service=settings.app_name)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the failure in full, return a response that leaks nothing."""
    log.exception(
        "request.unhandled_exception",
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Takes optional settings so that tests can construct an app against a
    specific configuration without mutating process-wide state.
    """
    settings = settings or get_settings()
    configure_logging(settings)

    # Interactive docs are useful in development and an information leak in
    # production, so they are withheld there.
    expose_docs = not settings.is_production

    app = FastAPI(
        title="Energy-Transfer API",
        description=DESCRIPTION,
        version=settings.app_version,
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", tags=["meta"], summary="Service metadata")
    async def root() -> dict[str, str]:
        """Identify the service and point at its documentation."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "environment": settings.app_env.value,
            "docs": "/docs" if expose_docs else "disabled",
            "health": f"{settings.api_v1_prefix}/health/ready",
        }

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        """Expose Prometheus metrics."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
