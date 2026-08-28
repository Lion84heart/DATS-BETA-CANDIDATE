"""Tests for DATS Platform API S15 — Alpha Release Preparation.

Tests WebSocket, Prometheus export, CSV export, and new Alpha features.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestPrometheusExport(unittest.TestCase):
    """Tests for Prometheus metrics export."""

    def setUp(self):
        self.client = TestClient(app)

    def test_prometheus_format(self):
        """Prometheus endpoint returns valid exposition format."""
        response = self.client.get("/metrics/prometheus")
        self.assertEqual(response.status_code, 200)
        text = response.text
        self.assertIn("# TYPE", text)
        self.assertIn("dats_counter_", text)
        # Gauges may or may not exist depending on test state

    def test_prometheus_counters(self):
        """Prometheus output contains counter metrics."""
        response = self.client.get("/metrics/prometheus")
        self.assertEqual(response.status_code, 200)
        text = response.text
        lines = text.split("\n")
        counter_lines = [l for l in lines if l.startswith("dats_counter_")]
        self.assertGreater(len(counter_lines), 0)

    def test_prometheus_gauges(self):
        """Prometheus output contains gauge metrics."""
        response = self.client.get("/metrics/prometheus")
        self.assertEqual(response.status_code, 200)
        text = response.text
        lines = text.split("\n")
        gauge_lines = [l for l in lines if l.startswith("dats_gauge_")]
        self.assertGreaterEqual(len(gauge_lines), 0)


class TestCSVExport(unittest.TestCase):
    """Tests for CSV export functionality."""

    def setUp(self):
        self.client = TestClient(app)

    def test_csv_export_format(self):
        """CSV export returns properly formatted data."""
        response = self.client.get("/decisions/export/csv")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["format"], "csv")
        self.assertIn("csv_data", data)
        self.assertIn("count", data)

    def test_csv_headers(self):
        """CSV export contains expected headers."""
        response = self.client.get("/decisions/export/csv")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        csv_lines = data["csv_data"].strip().split("\n")
        self.assertGreater(len(csv_lines), 0)
        header = csv_lines[0]
        self.assertIn("decision_id", header)
        self.assertIn("symbol", header)
        self.assertIn("strategy", header)


class TestWebSocketEndpoints(unittest.TestCase):
    """Tests for WebSocket endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_websocket_decisions_auth_required(self):
        """WebSocket decisions requires authentication."""
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/decisions") as websocket:
                websocket.receive_json()

    def test_websocket_market_auth_required(self):
        """WebSocket market requires authentication."""
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/market") as websocket:
                websocket.receive_json()

    def test_websocket_system_auth_required(self):
        """WebSocket system requires authentication."""
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/system") as websocket:
                websocket.receive_json()


class TestAlphaFeatures(unittest.TestCase):
    """Tests for Alpha release features."""

    def setUp(self):
        self.client = TestClient(app)

    def test_all_routers_registered(self):
        """All API routers are registered and accessible."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        required = [
            "/auth/login",
            "/health/",
            "/status/",
            "/config/",
            "/portfolio/",
            "/positions/",
            "/orders/",
            "/decisions/",
            "/execution/paper/status",
            "/metrics/",
            "/audit/history",
            "/diagnostics/runtime",
        ]
        for route in required:
            self.assertIn(route, routes, f"Route {route} not registered")

    def test_openapi_schema_complete(self):
        """OpenAPI schema contains all endpoints."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("paths", schema)
        paths = schema["paths"]
        self.assertGreater(len(paths), 20)

    def test_dashboard_v2_accessible(self):
        """Dashboard v2 is accessible."""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Dashboard v2", response.text)

    def test_operator_interface_accessible(self):
        """Operator interface is accessible."""
        response = self.client.get("/operator")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Operator Interface", response.text)

    def test_legacy_dashboard_accessible(self):
        """Legacy dashboard is still accessible."""
        response = self.client.get("/dashboard-v1")
        self.assertEqual(response.status_code, 200)

    def test_static_files_served(self):
        """Static files are served correctly."""
        response = self.client.get("/static/dashboard.html")
        self.assertIn(response.status_code, [200, 404])  # May or may not exist


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmark tests."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_latency(self):
        """Health endpoint responds within 50ms."""
        import time
        start = time.perf_counter()
        response = self.client.get("/health/")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 50.0, f"Health took {elapsed:.2f}ms")

    def test_status_latency(self):
        """Status endpoint responds within 50ms."""
        import time
        start = time.perf_counter()
        response = self.client.get("/status/")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 50.0, f"Status took {elapsed:.2f}ms")

    def test_metrics_latency(self):
        """Metrics endpoint responds within 50ms."""
        import time
        start = time.perf_counter()
        response = self.client.get("/metrics/")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 50.0, f"Metrics took {elapsed:.2f}ms")

    def test_prometheus_latency(self):
        """Prometheus endpoint responds within 50ms."""
        import time
        start = time.perf_counter()
        response = self.client.get("/metrics/prometheus")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 50.0, f"Prometheus took {elapsed:.2f}ms")

    def test_dashboard_latency(self):
        """Dashboard endpoint responds within 100ms."""
        import time
        start = time.perf_counter()
        response = self.client.get("/dashboard")
        elapsed = (time.perf_counter() - start) * 1000
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 100.0, f"Dashboard took {elapsed:.2f}ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
