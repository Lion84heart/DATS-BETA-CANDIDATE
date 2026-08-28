"""Metrics collection and time-series storage.

Implements a lightweight in-memory metrics collector suitable for
high-frequency trading with configurable retention and aggregation.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class MetricType(Enum):
    """Types of metrics supported."""

    COUNTER = auto()    # Monotonically increasing (e.g., requests served)
    GAUGE = auto()      # Point-in-time value (e.g., current memory)
    HISTOGRAM = auto()  # Distribution of values (e.g., latency)
    TIMER = auto()      # Duration measurement


@dataclass(frozen=True)
class MetricValue:
    """A single metric observation."""

    name: str
    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class MetricSnapshot:
    """Aggregated snapshot of a metric."""

    name: str
    count: int
    sum_value: float
    min_value: float
    max_value: float
    avg_value: float
    p50: float
    p95: float
    p99: float
    last_value: float
    timestamp: float


class MetricsCollector:
    """Thread-safe metrics collector with configurable retention.

    Stores metrics in memory with time-bucketed aggregation.
    Suitable for real-time dashboards and alerting.
    """

    def __init__(
        self,
        max_data_points: int = 10000,
        default_tags: dict[str, str] | None = None,
    ):
        """Initialize metrics collector.

        Args:
            max_data_points: Maximum data points per metric before rotation.
            default_tags: Tags applied to all metrics.
        """
        self._max_points = max_data_points
        self._default_tags = default_tags or {}
        self._metrics: dict[str, deque[MetricValue]] = defaultdict(
            lambda: deque(maxlen=max_data_points)
        )
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, MetricValue] = {}
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[MetricValue], None]] = []

    def record(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a metric value.

        Args:
            name: Metric name.
            value: Metric value.
            metric_type: Type of metric.
            tags: Additional dimension tags.
        """
        merged_tags = {**self._default_tags, **(tags or {})}
        mv = MetricValue(
            name=name,
            value=value,
            timestamp=time.time(),
            tags=merged_tags,
            metric_type=metric_type,
        )

        with self._lock:
            if metric_type == MetricType.COUNTER:
                self._counters[name] += value
                mv = MetricValue(
                    name=name,
                    value=self._counters[name],
                    timestamp=mv.timestamp,
                    tags=merged_tags,
                    metric_type=metric_type,
                )
                self._metrics[name].append(mv)
            elif metric_type == MetricType.GAUGE:
                self._gauges[name] = mv
                self._metrics[name].append(mv)
            else:
                self._metrics[name].append(mv)

        for cb in self._callbacks:
            try:
                cb(mv)
            except Exception:
                pass

    def increment(self, name: str, value: float = 1.0, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        self.record(name, value, MetricType.COUNTER, tags)

    def gauge(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        self.record(name, value, MetricType.GAUGE, tags)

    def timer(self, name: str, duration_ms: float, tags: dict[str, str] | None = None) -> None:
        """Record a timer metric in milliseconds."""
        self.record(name, duration_ms, MetricType.TIMER, tags)

    def histogram(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a histogram observation."""
        self.record(name, value, MetricType.HISTOGRAM, tags)

    def time(self, name: str, tags: dict[str, str] | None = None):
        """Context manager for timing a block of code.

        Usage:
            with collector.time("operation"):
                do_work()
        """
        return _TimerContext(self, name, tags)

    def snapshot(self, name: str) -> MetricSnapshot | None:
        """Get aggregated snapshot for a metric.

        Returns:
            MetricSnapshot with statistics, or None if no data.
        """
        with self._lock:
            values = list(self._metrics.get(name, []))
            if not values:
                return None

        vals = [v.value for v in values]
        sorted_vals = sorted(vals)
        n = len(sorted_vals)

        def percentile(p: float) -> float:
            idx = int(n * p / 100.0)
            return sorted_vals[max(0, min(idx, n - 1))]

        return MetricSnapshot(
            name=name,
            count=n,
            sum_value=sum(vals),
            min_value=min(vals),
            max_value=max(vals),
            avg_value=sum(vals) / n,
            p50=percentile(50),
            p95=percentile(95),
            p99=percentile(99),
            last_value=vals[-1],
            timestamp=time.time(),
        )

    def get_all_snapshots(self) -> dict[str, MetricSnapshot]:
        """Get snapshots for all metrics."""
        with self._lock:
            names = list(self._metrics.keys())
        return {name: snap for name in names if (snap := self.snapshot(name))}

    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        with self._lock:
            return self._counters.get(name, 0.0)

    def get_gauge(self, name: str) -> float | None:
        """Get current gauge value."""
        with self._lock:
            g = self._gauges.get(name)
            return g.value if g else None

    def on_metric(self, callback: Callable[[MetricValue], None]) -> None:
        """Register callback for new metric values."""
        self._callbacks.append(callback)

    def clear(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()


class _TimerContext:
    """Context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, name: str, tags: dict[str, str] | None):
        self.collector = collector
        self.name = name
        self.tags = tags
        self.start: float = 0.0

    def __enter__(self) -> "_TimerContext":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        duration_ms = (time.perf_counter() - self.start) * 1000.0
        self.collector.timer(self.name, duration_ms, self.tags)
