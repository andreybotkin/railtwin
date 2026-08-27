import logging

import structlog


class ProbeAccessFilter(logging.Filter):
    """Drop high-frequency Kubernetes probe access records."""

    _PROBE_PATHS = frozenset({"/health", "/ready"})

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 3:
            return True

        path = args[2]
        if not isinstance(path, str):
            return True

        return path.partition("?")[0] not in self._PROBE_PATHS


def configure_logging(log_level: str = "INFO") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, ProbeAccessFilter) for item in access_logger.filters):
        access_logger.addFilter(ProbeAccessFilter())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)
