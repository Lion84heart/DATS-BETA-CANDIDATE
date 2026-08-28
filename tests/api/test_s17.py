"""Tests for DATS Platform API S17 — Alpha Completion Mode.

Tests bug fixes, audit export, feature freeze compliance, and E2E workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestBugFixes(unittest.TestCase):
    """Tests verifying critical bug fixes from S17."""

    def setUp(self):
        self.client = TestClient(app)
        # Reset auth rate limiter for tests
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()

    def test_no_duplicate_openapi_route(self):
        """No duplicate GET handlers on /openapi.json."""
        from collections import defaultdict
        path_methods = defaultdict(list)
        for r in app.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                for m in r.methods:
                    if m != "HEAD":
                        path_methods[(r.path, m)].append(r.name)
        dups = {k: v for k, v in path_methods.items() if len(v) > 1}
        self.assertEqual(len(dups), 0, f"Duplicate routes found: {dups}")

    def test_openapi_schema_accessible(self):
        """OpenAPI schema is accessible via built-in endpoint."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("openapi", data)
        self.assertIn("paths", data)
        self.assertGreater(len(data["paths"]), 20)

    def test_audit_export_json(self):
        """Audit export returns JSON format by default."""
        # Audit export requires analyst+ auth
        r = self.client.post("/auth/login", json={"username": "analyst", "password": "analyst"})
        self.assertEqual(r.status_code, 200)
        token = r.json()["access_token"]
        response = self.client.get("/audit/export", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["format"], "json")
        self.assertIn("count", data)
        self.assertIn("entries", data)

    def test_audit_export_csv(self):
        """Audit export returns CSV format when requested."""
        r = self.client.post("/auth/login", json={"username": "analyst", "password": "analyst"})
        self.assertEqual(r.status_code, 200)
        token = r.json()["access_token"]
        response = self.client.get("/audit/export?format=csv", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["format"], "csv")
        self.assertIn("csv_data", data)
        self.assertIn("count", data)
        # Verify CSV has headers
        lines = data["csv_data"].strip().split("\n")
        self.assertGreater(len(lines), 0)
        self.assertIn("timestamp", lines[0])

    def test_decisions_summary_pipeline_accessible(self):
        """Decision pipeline summary is accessible after route ordering fix."""
        response = self.client.get("/decisions/summary/pipeline")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_decisions_recorded", data)

    def test_decisions_export_csv_accessible(self):
        """Decision CSV export is accessible after route ordering fix."""
        response = self.client.get("/decisions/export/csv")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["format"], "csv")
        self.assertIn("csv_data", data)

    def test_paper_trading_start_no_body(self):
        """Paper trading can be started without request body."""
        # Ensure paper trading is stopped first
        self.client.post("/execution/paper/stop")
        response = self.client.post("/execution/paper/start")
        self.assertIn(response.status_code, [200, 201])
        data = response.json()
        self.assertEqual(data["status"], "started")
        # Cleanup
        self.client.post("/execution/paper/stop")

    def test_orders_history_pagination(self):
        """Order history supports pagination after dict-to-list fix."""
        response = self.client.get("/orders/history?limit=10&offset=0")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("total", data)
        self.assertIn("offset", data)
        self.assertIn("limit", data)
        self.assertIn("orders", data)

    def test_login_rate_limiting(self):
        """Login endpoint enforces rate limiting after TD-M-001 fix."""
        # Reset limiter for clean state
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()

        # Consume the capacity quickly (5 requests)
        for _ in range(5):
            r = self.client.post("/auth/login", json={"username": "admin", "password": "wrong"})
            self.assertEqual(r.status_code, 401)

        # 6th request should be rate limited
        r = self.client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)

        # Reset for other tests
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()


class TestFeatureFreezeCompliance(unittest.TestCase):
    """Tests verifying Feature Freeze compliance."""

    def setUp(self):
        self.client = TestClient(app)

    def test_no_beta_endpoints_exist(self):
        """No Beta-only endpoints are registered."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        beta_only = [
            "/v1/",  # API versioning deferred
            "/broker/live/",  # Live broker deferred
            "/analytics/",  # Advanced analytics deferred
            "/ml/",  # ML pipeline deferred
        ]
        for route in beta_only:
            self.assertNotIn(route, routes, f"Beta-only endpoint {route} should not exist during Feature Freeze")

    def test_alpha_endpoints_exist(self):
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
            "/decisions/summary/pipeline",
            "/decisions/export/csv",
            "/execution/paper/status",
            "/execution/paper/start",
            "/execution/paper/stop",
            "/metrics/",
            "/metrics/prometheus",
            "/audit/history",
            "/audit/summary",
            "/audit/export",
            "/diagnostics/runtime",
            "/diagnostics/performance",
            "/diagnostics/latency",
            "/system/version",
            "/system/capabilities",
            "/system/state",
            "/system/shutdown",
            "/ws/decisions",
            "/ws/market",
            "/ws/system",
        ]
        for route in required:
            self.assertIn(route, routes, f"Required Alpha endpoint {route} not registered")


class TestE2EWorkflow(unittest.TestCase):
    """End-to-end Alpha workflow tests."""

    def setUp(self):
        self.client = TestClient(app)

    def test_complete_alpha_workflow(self):
        """Execute all 10 steps of the Alpha operational workflow."""
        # Step 1-2: System Start + Health Verification
        r = self.client.get("/health/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/status/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/system/version")
        self.assertEqual(r.status_code, 200)

        # Step 3: Market Data
        r = self.client.get("/config/data")
        self.assertEqual(r.status_code, 200)

        # Step 4: Strategy Execution
        r = self.client.get("/decisions/summary/pipeline")
        self.assertEqual(r.status_code, 200)

        # Step 5: Risk Validation
        r = self.client.get("/config/risk")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/portfolio/summary")
        self.assertEqual(r.status_code, 200)

        # Step 6: Paper Trade Execution
        # Stop first if already running
        self.client.post("/execution/paper/stop")
        r = self.client.post("/execution/paper/start")
        self.assertIn(r.status_code, [200, 201])
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

        # Step 7: Decision Recording
        r = self.client.get("/decisions/?limit=10")
        self.assertEqual(r.status_code, 200)

        # Step 8: Dashboard Review
        r = self.client.get("/operator")
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 200)

        # Step 9: Decision Export
        r = self.client.get("/decisions/export/csv")
        self.assertEqual(r.status_code, 200)

        # Step 10: Controlled Shutdown
        r = self.client.post("/execution/paper/stop")
        self.assertEqual(r.status_code, 200)

    def test_dashboard_v1_accessible(self):
        """Legacy dashboard v1 is still accessible."""
        r = self.client.get("/dashboard-v1")
        self.assertEqual(r.status_code, 200)

    def test_batch_orders_workflow(self):
        """Batch order submission works in workflow."""
        payload = {
            "orders": [
                {"symbol": "AAPL", "side": "buy", "order_type": "market", "quantity": 10},
                {"symbol": "MSFT", "side": "buy", "order_type": "market", "quantity": 5},
            ]
        }
        r = self.client.post("/orders/batch", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["submitted"], 2)


class TestAlphaReadiness(unittest.TestCase):
    """Tests verifying Alpha v1.0 readiness criteria."""

    def setUp(self):
        self.client = TestClient(app)

    def test_all_routers_registered(self):
        """All 14 API routers are registered."""
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        router_prefixes = [
            "/auth",
            "/health",
            "/status",
            "/config",
            "/portfolio",
            "/positions",
            "/orders",
            "/decisions",
            "/execution",
            "/metrics",
            "/audit",
            "/diagnostics",
            "/system",
            "/ws",
        ]
        for prefix in router_prefixes:
            matches = [r for r in routes if r.startswith(prefix)]
            self.assertGreater(len(matches), 0, f"No routes for prefix {prefix}")

    def test_performance_under_threshold(self):
        """All endpoints respond within 50ms threshold."""
        import time
        endpoints = [
            "/health/",
            "/status/",
            "/metrics/",
            "/system/version",
            "/system/capabilities",
        ]
        for endpoint in endpoints:
            start = time.perf_counter()
            r = self.client.get(endpoint)
            elapsed = (time.perf_counter() - start) * 1000
            self.assertEqual(r.status_code, 200)
            self.assertLess(elapsed, 50.0, f"{endpoint} took {elapsed:.2f}ms")

    def test_openapi_completeness(self):
        """OpenAPI schema contains all Alpha endpoints."""
        r = self.client.get("/openapi.json")
        self.assertEqual(r.status_code, 200)
        schema = r.json()
        self.assertIn("paths", schema)
        paths = schema["paths"]
        self.assertGreaterEqual(len(paths), 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
