"""Tests for system bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from system.bootstrap import SystemBootstrap
from system.config_loader import ConfigLoader


class TestSystemBootstrap(unittest.TestCase):
    """Tests for SystemBootstrap."""

    def tearDown(self):
        """Clean environment variables."""
        for key in list(os.environ.keys()):
            if key.startswith("DATS_") or key.startswith("TEST_"):
                del os.environ[key]

    def test_bootstrap_success(self):
        """Successful bootstrap returns all components."""
        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()

        self.assertTrue(result.success)
        self.assertIsNotNone(result.lifecycle)
        self.assertIsNotNone(result.registry)
        self.assertEqual(result.errors, [])

    def test_bootstrap_registers_components(self):
        """Bootstrap registers all subsystems."""
        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()

        registry = result.registry
        self.assertTrue(registry.has("metrics"))
        self.assertTrue(registry.has("alerts"))
        self.assertTrue(registry.has("health"))
        self.assertTrue(registry.has("logger"))
        self.assertTrue(registry.has("audit"))
        self.assertTrue(registry.has("decision_store"))
        self.assertTrue(registry.has("feed"))
        self.assertTrue(registry.has("broker"))
        self.assertTrue(registry.has("portfolio"))
        self.assertTrue(registry.has("risk_manager"))
        self.assertTrue(registry.has("execution_engine"))

    def test_bootstrap_with_invalid_config(self):
        """Invalid config fails validation."""
        os.environ["DATS_INITIAL_CAPITAL"] = "0"
        config = ConfigLoader()
        bootstrap = SystemBootstrap(config_loader=config)
        result = bootstrap.bootstrap()

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("INITIAL_CAPITAL", result.errors[0])

    def test_bootstrap_with_custom_prefix(self):
        """Bootstrap with custom config prefix."""
        os.environ["MYAPP_INITIAL_CAPITAL"] = "500000"
        config = ConfigLoader(prefix="MYAPP_")
        bootstrap = SystemBootstrap(config_loader=config)
        result = bootstrap.bootstrap()

        self.assertTrue(result.success)
        self.assertEqual(result.registry, result.registry)

    def test_bootstrap_registry_types(self):
        """Registry components have correct types."""
        from observability.metrics import MetricsCollector
        from observability.alerts import AlertManager
        from observability.health import HealthCheck
        from observability.logging import StructuredLogger
        from security.audit import AuditLogger
        from intelligence.decisions import DecisionStore

        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()
        registry = result.registry

        self.assertIsInstance(registry.get("metrics"), MetricsCollector)
        self.assertIsInstance(registry.get("alerts"), AlertManager)
        self.assertIsInstance(registry.get("health"), HealthCheck)
        self.assertIsInstance(registry.get("logger"), StructuredLogger)
        self.assertIsInstance(registry.get("audit"), AuditLogger)
        self.assertIsInstance(registry.get("decision_store"), DecisionStore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
