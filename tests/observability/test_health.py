"""Tests for health checks."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from observability.health import (  # type: ignore
    HealthCheck,
    HealthCheckResult,
    HealthStatus,
    simple_check,
)


class TestHealthCheck(unittest.TestCase):
    """Tests for health check manager."""

    def setUp(self):
        self.health = HealthCheck("test-service", timeout_seconds=2.0)

    def test_simple_check(self):
        """Simple check helper creates correct result."""
        result = simple_check("memory", True)
        self.assertEqual(result.status, HealthStatus.HEALTHY)
        self.assertEqual(result.name, "memory")

    def test_simple_check_fail(self):
        """Simple check with failure."""
        result = simple_check("disk", False, "Disk full")
        self.assertEqual(result.status, HealthStatus.UNHEALTHY)
        self.assertEqual(result.message, "Disk full")

    def test_register_sync_check(self):
        """Register and run synchronous check."""
        self.health.register("db", lambda: simple_check("db", True))
        result = asyncio.run(self.health.run("db"))
        self.assertEqual(result.overall_status, HealthStatus.HEALTHY)
        self.assertEqual(len(result.checks), 1)

    def test_register_async_check(self):
        """Register and run async check."""
        async def async_check():
            return simple_check("cache", True)

        self.health.register("cache", async_check)
        result = asyncio.run(self.health.run("cache"))
        self.assertEqual(result.overall_status, HealthStatus.HEALTHY)

    def test_unhealthy_result(self):
        """Unhealthy check makes overall unhealthy."""
        self.health.register("db", lambda: simple_check("db", False))
        result = asyncio.run(self.health.run("db"))
        self.assertEqual(result.overall_status, HealthStatus.UNHEALTHY)

    def test_multiple_checks(self):
        """Multiple checks aggregated."""
        self.health.register("a", lambda: simple_check("a", True))
        self.health.register("b", lambda: simple_check("b", False))
        result = asyncio.run(self.health.run())
        self.assertEqual(result.overall_status, HealthStatus.UNHEALTHY)
        self.assertEqual(len(result.checks), 2)

    def test_degraded_status(self):
        """Degraded check sets degraded status."""
        def degraded_check():
            return HealthCheckResult(
                name="latency",
                status=HealthStatus.DEGRADED,
                response_time_ms=150.0,
                message="Slow but functional",
                timestamp=__import__('time').time(),
            )

        self.health.register("latency", degraded_check)
        result = asyncio.run(self.health.run("latency"))
        self.assertEqual(result.overall_status, HealthStatus.DEGRADED)

    def test_timeout(self):
        """Check timeout produces unhealthy result."""
        async def slow_check():
            await asyncio.sleep(5)
            return simple_check("slow", True)

        self.health.register("slow", slow_check)
        result = asyncio.run(self.health.run("slow"))
        self.assertEqual(result.overall_status, HealthStatus.UNHEALTHY)
        self.assertIn("timed out", result.checks[0].message.lower())

    def test_unknown_check(self):
        """Running unknown check returns unknown status."""
        result = asyncio.run(self.health.run("nonexistent"))
        self.assertEqual(result.checks[0].status, HealthStatus.UNKNOWN)

    def test_check_names(self):
        """Get registered check names."""
        self.health.register("a", lambda: simple_check("a", True))
        self.health.register("b", lambda: simple_check("b", True))
        names = self.health.check_names
        self.assertEqual(sorted(names), ["a", "b"])

    def test_uptime(self):
        """Uptime tracked."""
        result = asyncio.run(self.health.run())
        self.assertGreater(result.uptime_seconds, 0)

    def test_metadata(self):
        """Service metadata set."""
        self.health.set_metadata(version="1.0", region="us-east")
        # Metadata accessible through instance
        self.assertEqual(self.health._metadata["version"], "1.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
