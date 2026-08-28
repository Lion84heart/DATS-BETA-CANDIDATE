"""Tests for DATS Platform API."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from fastapi.testclient import TestClient

from api.main import app


def _get_auth_headers(client: TestClient, username: str = "admin", password: str = "admin") -> dict:
    """Authenticate and return headers with Bearer token."""
    response = client.post("/auth/login", json={"username": username, "password": password})
    if response.status_code == 200:
        token = response.json().get("access_token", "")
        return {"Authorization": f"Bearer {token}"}
    return {}


# Module-level token cache to avoid rate limiting during test runs
_token_cache: dict[str, dict] = {}


def _get_cached_auth_headers(client: TestClient, username: str = "admin", password: str = "admin") -> dict:
    """Get cached auth headers or login if not cached."""
    key = f"{username}:{password}"
    if key not in _token_cache:
        _token_cache[key] = _get_auth_headers(client, username, password)
    return _token_cache[key]


class TestAPIRoot(unittest.TestCase):
    """Tests for API root and basic endpoints."""

    def setUp(self):
        """Create test client."""
        self.client = TestClient(app)

    def test_root(self):
        """API root returns version."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("DATS Platform API", response.text)

    def test_openapi_schema(self):
        """OpenAPI schema is accessible."""
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["info"]["title"], "DATS Platform API")

    def test_dashboard(self):
        """Dashboard endpoint returns HTML."""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])


class TestHealthEndpoints(unittest.TestCase):
    """Tests for health endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_overall(self):
        """Health endpoint returns status."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("checks", data)

    def test_health_check_detail(self):
        """Specific health check returns detail."""
        response = self.client.get("/health/system_uptime")
        self.assertIn(response.status_code, [200, 404])  # May or may not exist


class TestStatusEndpoints(unittest.TestCase):
    """Tests for status endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_system_status(self):
        """Status endpoint returns system state."""
        response = self.client.get("/status/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("state", data)
        self.assertIn("uptime_seconds", data)
        self.assertIn("is_running", data)

    def test_component_status(self):
        """Component status lists registered components."""
        response = self.client.get("/status/components")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("components", data)
        self.assertIn("count", data)
        self.assertGreater(data["count"], 0)

    def test_lifecycle_transitions(self):
        """Lifecycle transitions endpoint."""
        response = self.client.get("/status/transitions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("transitions", data)
        self.assertIn("count", data)


class TestConfigEndpoints(unittest.TestCase):
    """Tests for config endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        self.headers = _get_cached_auth_headers(self.client, "viewer", "viewer")

    def test_full_config(self):
        """Full config endpoint."""
        response = self.client.get("/config/", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("trading", data)
        self.assertIn("risk", data)
        self.assertIn("data", data)
        self.assertIn("monitoring", data)

    def test_trading_config(self):
        """Trading config section."""
        response = self.client.get("/config/trading", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("initial_capital", data)

    def test_risk_config(self):
        """Risk config section."""
        response = self.client.get("/config/risk", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("var_confidence", data)

    def test_config_validation(self):
        """Config validation endpoint."""
        response = self.client.get("/config/validate", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("valid", data)
        self.assertIn("errors", data)


class TestPortfolioEndpoints(unittest.TestCase):
    """Tests for portfolio endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_portfolio(self):
        """Portfolio endpoint returns account state."""
        response = self.client.get("/portfolio/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cash", data)
        self.assertIn("total_value", data)
        self.assertIn("positions", data)

    def test_positions(self):
        """Positions endpoint."""
        response = self.client.get("/portfolio/positions")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("positions", data)

    def test_portfolio_summary(self):
        """Portfolio summary endpoint."""
        response = self.client.get("/portfolio/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cash", data)
        self.assertIn("total_pnl", data)


class TestDecisionsEndpoints(unittest.TestCase):
    """Tests for decisions endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        self.headers = _get_cached_auth_headers(self.client, "viewer", "viewer")

    def test_list_decisions(self):
        """List decisions endpoint."""
        response = self.client.get("/decisions/?limit=10", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("records", data)

    def test_decision_not_found(self):
        """Non-existent decision returns 404."""
        response = self.client.get("/decisions/nonexistent-id", headers=self.headers)
        self.assertEqual(response.status_code, 404)

    def test_pipeline_summary(self):
        """Pipeline summary endpoint."""
        response = self.client.get("/decisions/summary/pipeline", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_decisions_recorded", data)


class TestExecutionEndpoints(unittest.TestCase):
    """Tests for execution endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        self.headers = _get_cached_auth_headers(self.client, "operator", "operator")

    def test_paper_trading_status_not_running(self):
        """Paper trading status when not running."""
        response = self.client.get("/execution/paper/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["running"], False)

    def test_stop_paper_not_running(self):
        """Stop paper trading when not running returns 409."""
        response = self.client.post("/execution/paper/stop", headers=self.headers)
        self.assertEqual(response.status_code, 409)


class TestMetricsEndpoints(unittest.TestCase):
    """Tests for metrics endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_all_metrics(self):
        """All metrics endpoint."""
        response = self.client.get("/metrics/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("counters", data)
        self.assertIn("gauges", data)

    def test_counter(self):
        """Specific counter endpoint."""
        response = self.client.get("/metrics/counter/system.startup")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("name", data)
        self.assertIn("value", data)

    def test_metrics_snapshot(self):
        """Metrics snapshot endpoint."""
        response = self.client.get("/metrics/snapshot")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("counters", data)
        self.assertIn("histogram_stats", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
