"""Structured logging with JSON output and context propagation.

Provides correlation IDs, trace context, and structured fields
for log aggregation and analysis.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# Context variables for request tracing
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)


@dataclass(frozen=True)
class LogEntry:
    """A structured log entry."""

    timestamp: str
    level: str
    message: str
    logger: str
    correlation_id: str | None
    trace_id: str | None
    span_id: str | None
    source_file: str | None
    source_line: int | None
    extra: dict[str, Any] = field(default_factory=dict)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": getattr(record, "correlation_id", None),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
            "source": {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            },
        }
        # Add extra fields
        for key in ["event_type", "component", "operation", "duration_ms", "error"]:
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        # Add any custom extra fields
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)

        return json.dumps(entry, default=str)


class StructuredLogger:
    """Structured logger with context propagation.

    Usage:
        logger = StructuredLogger("trading.engine")
        logger.info("Order submitted", order_id="123", symbol="AAPL")
    """

    def __init__(self, name: str, level: int = logging.INFO):
        """Initialize structured logger.

        Args:
            name: Logger name (typically module.component).
            level: Minimum log level.
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(level)
        self._logger.handlers = []
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        self._logger.addHandler(handler)
        self.name = name

    def _log(self, level: int, message: str, **kwargs: Any) -> None:
        """Internal log method with context injection."""
        extra = {
            "correlation_id": _correlation_id.get(),
            "trace_id": _trace_id.get(),
            "span_id": _span_id.get(),
        }
        if kwargs:
            extra["extra_fields"] = kwargs
        self._logger.log(level, message, extra=extra)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self._log(logging.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        self._log(logging.CRITICAL, message, **kwargs)

    def event(self, event_type: str, message: str, **kwargs: Any) -> None:
        """Log a business event.

        Args:
            event_type: Event classification (e.g., "order.submitted").
            message: Human-readable description.
            **kwargs: Event fields.
        """
        kwargs["event_type"] = event_type
        self._log(logging.INFO, message, **kwargs)

    @staticmethod
    def set_correlation_id(cid: str | None) -> None:
        """Set correlation ID for current context."""
        _correlation_id.set(cid)

    @staticmethod
    def set_trace_context(trace_id: str | None, span_id: str | None) -> None:
        """Set distributed tracing context."""
        _trace_id.set(trace_id)
        _span_id.set(span_id)

    @staticmethod
    def get_correlation_id() -> str | None:
        """Get current correlation ID."""
        return _correlation_id.get()

    @staticmethod
    def get_trace_context() -> tuple[str | None, str | None]:
        """Get current trace context."""
        return (_trace_id.get(), _span_id.get())

    @staticmethod
    def clear_context() -> None:
        """Clear all context variables."""
        _correlation_id.set(None)
        _trace_id.set(None)
        _span_id.set(None)
