"""Tests for DATS Platform API S14 — Authentication, Positions, Orders, Audit, Diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from fastapi.testclient import TestClient

from api.main import app


class TestAuthEndpoints(unittest.TestCase):
    """Tests for authentication endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        # Reset auth rate limiter for tests
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()

    def test_login_success(self):
        """Login with valid credentials returns token."""
        response = self.client.post("/auth/login", json={"username": "admin", "password": "admin"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertEqual(data["role"], "admin")

    def test_login_failure(self):
        """Login with invalid credentials returns 401."""
        response = self.client.post("/auth/login", json={"username": "admin", "password": "wrong"})
        self.assertEqual(response.status_code, 401)

    def test_get_me(self):
        """Get current user with valid token."""
        login = self.client.post("/auth/login", json={"username": "operator", "password": "operator"})
        token = login.json()["access_token"]
        response = self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["username"], "operator")
        self.assertEqual(data["role"], "operator")

    def test_get_me_no_token(self):
        """Get current user without token returns 401."""
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_logout(self):
        """Logout endpoint works."""
        response = self.client.post("/auth/logout")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "logged_out")

    def test_sessions_admin_only(self):
        """Sessions endpoint requires admin."""
        login = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer"})
        token = login.json()["access_token"]
        response = self.client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 403)

    def test_sessions_admin(self):
        """Admin can list sessions."""
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin"})
        token = login.json()["access_token"]
        response = self.client.get("/auth/sessions", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("sessions", data)


class TestPositionsEndpoints(unittest.TestCase):
    """Tests for positions endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_list_positions(self):
        """List positions endpoint."""
        response = self.client.get("/positions/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("positions", data)

    def test_position_not_found(self):
        """Non-existent position returns 404."""
        response = self.client.get("/positions/NONEXISTENT")
        self.assertEqual(response.status_code, 404)

    def test_positions_summary(self):
        """Positions summary endpoint."""
        response = self.client.get("/positions/summary/overview")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("position_count", data)
        self.assertIn("total_market_value", data)


class TestOrdersEndpoints(unittest.TestCase):
    """Tests for orders endpoints."""

    def setUp(self):
        self.client = TestClient(app)

    def test_list_orders(self):
        """List orders endpoint."""
        response = self.client.get("/orders/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("orders", data)

    def test_order_not_found(self):
        """Non-existent order returns 404."""
        response = self.client.get("/orders/nonexistent-id")
        self.assertEqual(response.status_code, 404)

    def test_create_order_validation(self):
        """Create order with invalid data returns error."""
        response = self.client.post("/orders/", json={
            "symbol": "AAPL",
            "side": "invalid",
            "order_type": "market",
            "quantity": 10,
        })
        self.assertEqual(response.status_code, 422)

    def test_cancel_order(self):
        """Cancel order endpoint works (paper broker accepts all cancels)."""
        response = self.client.delete("/orders/nonexistent-id")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")


class TestAuditEndpoints(unittest.TestCase):
    """Tests for audit endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        # Reset auth rate limiter for tests
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()

    def test_audit_history_no_auth(self):
        """Audit history requires authentication."""
        response = self.client.get("/audit/history")
        self.assertEqual(response.status_code, 401)

    def test_audit_history_viewer_denied(self):
        """Audit history requires analyst role."""
        login = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer"})
        token = login.json()["access_token"]
        response = self.client.get("/audit/history", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 403)

    def test_audit_history_analyst(self):
        """Analyst can access audit history."""
        login = self.client.post("/auth/login", json={"username": "analyst", "password": "analyst"})
        token = login.json()["access_token"]
        response = self.client.get("/audit/history", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("entries", data)
        self.assertIn("count", data)

    def test_audit_summary(self):
        """Audit summary endpoint."""
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin"})
        token = login.json()["access_token"]
        response = self.client.get("/audit/summary", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_entries", data)
        self.assertIn("action_breakdown", data)


class TestDiagnosticsEndpoints(unittest.TestCase):
    """Tests for diagnostics endpoints."""

    def setUp(self):
        self.client = TestClient(app)
        # Reset auth rate limiter for tests
        if hasattr(app.state, "auth_rate_limiter"):
            app.state.auth_rate_limiter._buckets.clear()
            app.state.auth_rate_limiter._last_access.clear()

    def test_runtime_no_auth(self):
        """Runtime diagnostics require authentication."""
        response = self.client.get("/diagnostics/runtime")
        self.assertEqual(response.status_code, 401)

    def test_runtime_viewer_denied(self):
        """Runtime diagnostics require operator role."""
        login = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer"})
        token = login.json()["access_token"]
        response = self.client.get("/diagnostics/runtime", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 403)

    def test_runtime_operator(self):
        """Operator can access runtime diagnostics."""
        login = self.client.post("/auth/login", json={"username": "operator", "password": "operator"})
        token = login.json()["access_token"]
        response = self.client.get("/diagnostics/runtime", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("python_version", data)
        self.assertIn("asyncio", data)

    def test_memory_diagnostics(self):
        """Memory diagnostics endpoint."""
        login = self.client.post("/auth/login", json={"username": "operator", "password": "operator"})
        token = login.json()["access_token"]
        response = self.client.get("/diagnostics/memory", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("gc_generations", data)
        self.assertIn("tracked_objects", data)

    def test_system_diagnostics_admin(self):
        """System diagnostics require admin."""
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin"})
        token = login.json()["access_token"]
        response = self.client.get("/diagnostics/system", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("runtime", data)
        self.assertIn("memory", data)


class TestDashboardAndOperator(unittest.TestCase):
    """Tests for dashboard and operator interface."""

    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_v2(self):
        """Dashboard v2 returns HTML."""
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Dashboard v2", response.text)

    def test_dashboard_v1(self):
        """Legacy dashboard still accessible."""
        response = self.client.get("/dashboard-v1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])

    def test_operator_interface(self):
        """Operator interface returns HTML."""
        response = self.client.get("/operator")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Operator Interface", response.text)


class TestAPIWithAuth(unittest.TestCase):
    """Tests that existing API endpoints still work with S14 additions."""

    def setUp(self):
        self.client = TestClient(app)

    def test_health_still_works(self):
        """Health endpoint still accessible."""
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())

    def test_status_still_works(self):
        """Status endpoint still accessible."""
        response = self.client.get("/status/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("state", response.json())

    def test_portfolio_still_works(self):
        """Portfolio endpoint still accessible."""
        response = self.client.get("/portfolio/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("cash", response.json())

    def test_metrics_still_works(self):
        """Metrics endpoint still accessible."""
        response = self.client.get("/metrics/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("counters", response.json())


if __name__ == "__main__":
    unittest.main(verbosity=2)
