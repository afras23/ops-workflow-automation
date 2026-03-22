"""Structured JSON logging with correlation_id propagation.

Sets up a JSON formatter that embeds correlation_id from contextvars in
every log entry. Call configure_logging() once at application startup.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

# Fields present on every LogRecord — excluded from the structured extras dict
_STANDARD_LOG_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects for structured log sinks."""

    def format(self, record: logging.LogRecord) -> str:
        """Render a LogRecord as a JSON string.

        Args:
            record: The log record to format.

        Returns:
            Single-line JSON string with timestamp, level, logger, message,
            correlation_id, and any extra fields passed via extra={}.
        """
        log_entry: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_ctx.get(""),
        }

        # Merge structured fields injected via logger.info(..., extra={...})
        for field, value in record.__dict__.items():
            if field not in _STANDARD_LOG_FIELDS:
                log_entry[field] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the root logger with JSON output to stdout.

    Args:
        log_level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
