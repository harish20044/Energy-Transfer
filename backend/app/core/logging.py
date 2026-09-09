"""Structured logging.

Console-rendered while developing, JSON in production so that market ticks,
clearing prices and settlement events stay queryable in a log aggregator.
"""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog
from structlog.typing import Processor

from app.core.config import LogFormat, Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog and route stdlib/uvicorn logging through it."""
    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)

    shared: list[Processor] = [
        # Carries request_id (and later tick_id) into every line automatically.
        structlog.contextvars.merge_contextvars,
        # The non-stdlib variants are required here: WriteLoggerFactory below
        # emits straight to stdout rather than going through logging.Logger, so
        # the structlog.stdlib.* processors (which expect a `.name` attribute)
        # would raise. The logger name is bound in `get_logger` instead.
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    renderer: Processor
    if settings.log_format is LogFormat.JSON:
        shared.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Send anything still using the stdlib logger to the same stream.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)

    # uvicorn.access duplicates what our own middleware already records.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a logger that tags every line with ``name``.

    The name is bound into the event dict rather than taken from a stdlib
    logger, because this configuration writes to stdout directly.
    """
    # structlog.get_logger is typed as returning Any; narrow it so that callers
    # keep full type information under mypy --strict.
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger().bind(logger=name))
