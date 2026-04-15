"""Structured logging configuration.

This module configures structured logging using structlog for consistent
and parseable log output throughout the application.
"""

import logging
import sys
from typing import Any, cast

import structlog
from structlog.types import Processor

from app.core.config import settings


def setup_logging() -> None:
    """Configure structured logging for the application.

    Sets up structlog with processors for timestamp, log level, and JSON
    formatting in production or pretty-printed output in development.
    """
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.environment == "production":
        # JSON output for production
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty output for development
        shared_processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True, exception_formatter=structlog.dev.plain_traceback
            )
        )

    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )


def get_logger(name: str | None = None, **kwargs: Any) -> structlog.BoundLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically __name__ of the calling module).
        **kwargs: Additional context to bind to the logger.

    Returns:
        structlog.BoundLogger: Configured logger instance.
    """
    logger = cast(structlog.BoundLogger, structlog.get_logger(name))
    if kwargs:
        logger = cast(structlog.BoundLogger, logger.bind(**kwargs))
    return logger
