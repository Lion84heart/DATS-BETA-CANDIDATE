"""DATS Observability Module (M7).

Provides metrics collection, alerting, structured logging, and health checks
for the trading system.
"""

from __future__ import annotations

from .metrics import MetricsCollector, MetricType
from .alerts import AlertManager, AlertRule, AlertSeverity
from .logging import StructuredLogger
from .health import HealthCheck, HealthStatus

__all__ = [
    "MetricsCollector",
    "MetricType",
    "AlertManager",
    "AlertRule",
    "AlertSeverity",
    "StructuredLogger",
    "HealthCheck",
    "HealthStatus",
]
