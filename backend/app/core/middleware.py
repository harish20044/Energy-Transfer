"""Cross-cutting HTTP middleware."""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

REQUEST_ID_HEADER = "X-Request-ID"

log = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to every request, log the outcome, and time it.

    The id is bound into structlog's context variables, so every log line
    emitted anywhere downstream — including inside a market tick — carries it
    without needing it threaded through call signatures.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Bind request context, delegate, then record the result."""
        # Honour an upstream id when present so traces survive a proxy hop.
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log the timing here, but let the exception handler own the
            # stack trace so it is not recorded twice.
            log.warning(
                "request.failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id

        log.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
