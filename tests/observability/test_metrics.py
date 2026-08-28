"""Tests for metrics collection."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

# Import after path setup
from observability.metrics import MetricType, MetricsCollector  # type: ignore


class TestMetricsCollector(unittest.TestCase):
    """Tests for metrics collection."""

    def setUp(self):
        self.collector = MetricsCollector(max_data_points=1000)

    def test_counter(self):
        """Counter increments correctly."""
        self.collector.increment("requests", 1.0)
        self.collector.increment("requests", 2.0)
        self.assertEqual(self.collector.get_counter("requests"), 3.0)

    def test_gauge(self):
        """Gauge stores latest value."""
        self.collector.gauge("memory", 1024.0)
        self.assertEqual(self.collector.get_gauge("memory"), 1024.0)

        self.collector.gauge("memory", 2048.0)
        self.assertEqual(self.collector.get_gauge("memory"), 2048.0)

    def test_timer(self):
        """Timer records duration."""
        self.collector.timer("latency", 50.0)
        self.collector.timer("latency", 100.0)

        snap = self.collector.snapshot("latency")
        self.assertIsNotNone(snap)
        self.assertEqual(snap.count, 2)
        self.assertEqual(snap.avg_value, 75.0)

    def test_histogram(self):
        """Histogram records distribution."""
        for v in [10, 20, 30, 40, 50]:
            self.collector.histogram("sizes", float(v))

        snap = self.collector.snapshot("sizes")
        self.assertEqual(snap.count, 5)
        self.assertEqual(snap.min_value, 10.0)
        self.assertEqual(snap.max_value, 50.0)

    def test_percentiles(self):
        """Percentile calculations."""
        for i in range(1, 101):
            self.collector.timer("pct", float(i))

        snap = self.collector.snapshot("pct")
        self.assertGreaterEqual(snap.p50, 49)
        self.assertGreaterEqual(snap.p95, 94)
        self.assertGreaterEqual(snap.p99, 98)

    def test_timer_context(self):
        """Timer context manager records duration."""
        with self.collector.time("block"):
            time.sleep(0.01)

        snap = self.collector.snapshot("block")
        self.assertEqual(snap.count, 1)
        self.assertGreater(snap.last_value, 0)

    def test_default_tags(self):
        """Default tags applied to metrics."""
        c = MetricsCollector(default_tags={"env": "test"})
        c.gauge("cpu", 50.0)

        snap = c.snapshot("cpu")
        self.assertIsNotNone(snap)

    def test_clear(self):
        """Clear resets all metrics."""
        self.collector.gauge("x", 1.0)
        self.collector.clear()
        self.assertIsNone(self.collector.get_gauge("x"))

    def test_max_points(self):
        """Max data points enforced."""
        c = MetricsCollector(max_data_points=5)
        for i in range(10):
            c.gauge("limited", float(i))

        snap = c.snapshot("limited")
        self.assertEqual(snap.count, 5)  # Only last 5 kept

    def test_all_snapshots(self):
        """Get all snapshots."""
        self.collector.gauge("a", 1.0)
        self.collector.gauge("b", 2.0)
        snaps = self.collector.get_all_snapshots()
        self.assertEqual(len(snaps), 2)

    def test_callback(self):
        """Metric callback fired."""
        events = []
        self.collector.on_metric(lambda m: events.append(m.name))
        self.collector.gauge("test", 1.0)
        self.assertEqual(events, ["test"])

    def test_empty_snapshot(self):
        """Snapshot of nonexistent metric returns None."""
        self.assertIsNone(self.collector.snapshot("nonexistent"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
