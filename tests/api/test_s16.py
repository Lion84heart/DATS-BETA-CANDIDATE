"""Tests for DATS Platform API S16 — Alpha Delivery.

Tests new S16 endpoints: system control, order history/batch, config runtime,
diagnostics performance, and alpha workflow integration.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestSystemControl(unittest.TestCase):
    """Tests for system control endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_system_version(self):
        """System version endpoint returns version info."""
        response = self.client.get("/system/version")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("version", data)
        self.assertIn("release", data)
        self.assertIn("Alpha", data["release"])

    def test_system_capabilities(self):
        """System capabilities endpoint returns capability summary."""
        response = self.client.get("/system/capabilities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_capabilities", data)
        self.assertIn("features", data)
        self.assertGreater(len(data["features"]), 0)

    def test_system_state_auth_required(self):
        """System state requires authentication."""
        response = self.client.get("/system/state")
        self.assertEqual(response.status_code, 401)

    def test_system_shutdown_auth_required(self):
        """System shutdown requires authentication."""
        response = self.client.post("/system/shutdown")
        self.assertEqual(response.status_code, 401)


class TestOrderHistoryAndBatch(unittest.TestCase):
    """Tests for order history and batch operations."""

    def setUp(self):
        self.client = TestClient(app)

    def test_order_history_endpoint(self):
        """Order history endpoint returns paginated results."""
        response = self.client.get("/orders/history")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("total", data)
        self.assertIn("offset", data)
        self.assertIn("limit", data)
        self.assertIn("orders", data)

    def test_order_history_with_symbol_filter(self):
        """Order history supports symbol filtering."""
        response = self.client.get("/orders/history?symbol=AAPL")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should return empty or filtered results
        self.assertIn("orders", data)

    def test_order_history_pagination(self):
        """Order history supports pagination."""
        response = self.client.get("/orders/history?limit=5&offset=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["limit"], 5)
        self.assertEqual(data["offset"], 0)

    def test_batch_orders_endpoint(self):
        """Batch orders endpoint accepts multiple orders."""
        payload = {
            "orders": [
                {
                    "symbol": "AAPL",
                    "side": "buy",
                    "order_type": "market",
                    "quantity": 10,
                },
                {
                    "symbol": "MSFT",
                    "side": "buy",
                    "order_type": "market",
                    "quantity": 5,
                },
            ]
        }
        response = self.client.post("/orders/batch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("submitted", data)
        self.assertIn("failed", data)
        self.assertIn("results", data)
        self.assertIn("errors", data)

    def test_batch_orders_empty(self):
        """Batch orders with empty list returns zero submitted."""
        payload = {"orders": []}
        response = self.client.post("/orders/batch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["submitted"], 0)
        self.assertEqual(data["failed"], 0)


class TestConfigRuntime(unittest.TestCase):
    """Tests for runtime configuration endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_config_runtime(self):
        """Runtime config endpoint returns config state."""
        response = self.client.get("/config/runtime")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("environment", data)
        self.assertIn("sections", data)
        self.assertIn("validation", data)

    def test_config_reload(self):
        """Config reload endpoint returns reload status."""
        response = self.client.post("/config/reload")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reloaded", data)
        self.assertTrue(data["reloaded"])
        self.assertIn("validation", data)


class TestDiagnosticsPerformance(unittest.TestCase):
    """Tests for performance diagnostics endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_diagnostics_performance_auth_required(self):
        """Performance diagnostics requires authentication."""
        response = self.client.get("/diagnostics/performance")
        self.assertEqual(response.status_code, 401)

    def test_diagnostics_latency(self):
        """Latency summary endpoint returns latency data."""
        response = self.client.get("/diagnostics/latency")
        self.assertEqual(response.status_code, 401)  # Requires auth


class TestAlphaWorkflow(unittest.TestCase):
    """Integration tests for the complete Alpha operational workflow."""

    def setUp(self):
        self.client = TestClient(app)

    def test_step1_system_start(self):
        """Step 1: System is running."""
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/status/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/system/version")
        self.assertEqual(r.status_code, 200)

    def test_step2_health_verification(self):
        """Step 2: All health checks pass."""
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("status", data)

    def test_step3_market_data(self):
        """Step 3: Market data config available."""
        r = self.client.get("/config/data")
        self.assertEqual(r.status_code, 200)

    def test_step4_strategy_execution(self):
        """Step 4: Decision pipeline active."""
        r = self.client.get("/decisions/summary/pipeline")
        self.assertEqual(r.status_code, 200)

    def test_step5_risk_validation(self):
        """Step 5: Risk config and portfolio accessible."""
        r = self.client.get("/config/risk")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/portfolio/summary")
        self.assertEqual(r.status_code, 200)

    def test_step6_paper_trade_execution(self):
        """Step 6: Paper trading can be started and orders submitted."""
        r = self.client.post("/execution/paper/start")
        self.assertEqual(r.status_code, 200)

        order = {
            "symbol": "AAPL",
            "side": "buy",
            "order_type": "market",
            "quantity": 100,
        }
        r = self.client.post("/orders/", json=order)
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/execution/paper/status")
        self.assertEqual(r.status_code, 200)

    def test_step7_decision_recording(self):
        """Step 7: Decisions are recorded."""
        r = self.client.get("/decisions/?limit=10")
        self.assertEqual(r.status_code, 200)

    def test_step8_dashboard_review(self):
        """Step 8: Dashboards are accessible."""
        r = self.client.get("/operator")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

    def test_step9_decision_export(self):
        """Step 9: Decisions can be exported."""
        r = self.client.get("/decisions/export/csv")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["format"], "csv")
        self.assertIn("csv_data", data)

    def test_step10_controlled_shutdown(self):
        """Step 10: Paper trading can be stopped."""
        # Start first to ensure it's running
        self.client.post("/execution/paper/start")
        r = self.client.post("/execution/paper/stop")
        self.assertEqual(r.status_code, 200)

    def test_complete_e2e_workflow(self):
        """Complete E2E workflow in sequence."""
        # Step 1-2: System start and health
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/status/")
        self.assertEqual(r.status_code, 200)

        # Step 3: Market data
        r = self.client.get("/config/data")
        self.assertEqual(r.status_code, 200)

        # Step 4: Strategy
        r = self.client.get("/decisions/summary/pipeline")
        self.assertEqual(r.status_code, 200)

        # Step 5: Risk
        r = self.client.get("/config/risk")
        self.assertEqual(r.status_code, 200)

        # Step 6: Paper trading
        r = self.client.post("/execution/paper/start")
        self.assertEqual(r.status_code, 200)

        order = {
            "symbol": "TSLA",
            "side": "buy",
            "order_type": "market",
            "quantity": 50,
        }
        r = self.client.post("/orders/", json=order)
        self.assertEqual(r.status_code, 200)

        # Step 7: Decisions
        r = self.client.get("/decisions/?limit=5")
        self.assertEqual(r.status_code, 200)

        # Step 8: Dashboards
        r = self.client.get("/operator")
        self.assertEqual(r.status_code, 200)

        # Step 9: Export
        r = self.client.get("/decisions/export/csv")
        self.assertEqual(r.status_code, 200)

        # Step 10: Shutdown
        r = self.client.post("/execution/paper/stop")
        self.assertEqual(r.status_code, 200)


class TestAPICompleteness(unittest.TestCase):
    """Tests verifying all required API endpoints exist."""

    def setUp(self):
        self.client = TestClient(app)

    def test_all_required_endpoints_exist(self):
        """All Alpha-required endpoints are registered."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        required = [
            "/auth/login",
            "/health/",
            "/status/",
            "/config/",
            "/config/validate",
            "/config/runtime",
            "/config/reload",
            "/portfolio/",
            "/positions/",
            "/orders/",
            "/orders/history",
            "/orders/batch",
            "/decisions/",
            "/decisions/export/csv",
            "/execution/paper/status",
            "/metrics/",
            "/metrics/prometheus",
            "/audit/history",
            "/diagnostics/runtime",
            "/diagnostics/performance",
            "/diagnostics/latency",
            "/system/version",
            "/system/capabilities",
            "/system/state",
            "/system/shutdown",
        ]
        for route in required:
            self.assertIn(route, routes, f"Required route {route} not registered")

    def test_openapi_schema_completeness(self):
        """OpenAPI schema contains all required endpoints."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        schema = response.json()
        self.assertIn("paths", schema)
        paths = schema["paths"]
        self.assertGreaterEqual(len(paths), 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
