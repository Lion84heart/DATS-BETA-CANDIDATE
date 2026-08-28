"""Integration test for full system bootstrap."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from system.bootstrap import SystemBootstrap
from system.config_loader import ConfigLoader
from system.decision_pipeline import DecisionPipeline, PipelineContext


class TestSystemBootstrapIntegration(unittest.TestCase):
    """Integration tests for full system bootstrap."""

    def tearDown(self):
        """Clean environment."""
        for key in list(os.environ.keys()):
            if key.startswith("DATS_") or key.startswith("TEST_"):
                del os.environ[key]

    def test_bootstrap_to_lifecycle_start(self):
        """Bootstrap and start lifecycle."""
        import asyncio

        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()

        self.assertTrue(result.success)
        lifecycle = result.lifecycle

        # Start the system
        ok = asyncio.run(lifecycle.start())
        self.assertTrue(ok)
        self.assertEqual(lifecycle.state.name, "RUNNING")
        self.assertTrue(lifecycle.is_running)

        # Stop
        asyncio.run(lifecycle.stop())
        self.assertEqual(lifecycle.state.name, "STOPPED")

    def test_bootstrap_registers_lifecycle_hooks(self):
        """Lifecycle hooks are registered during bootstrap."""
        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()

        lifecycle = result.lifecycle
        transitions = lifecycle.get_transitions()
        # After bootstrap, should still be INITIALIZING (start() not called)
        self.assertEqual(lifecycle.state.name, "INITIALIZING")

        # But hooks should be registered (check by verifying on_startup/on_shutdown lists)
        # We can verify by starting and checking transitions
        import asyncio

        asyncio.run(lifecycle.start())
        self.assertEqual(lifecycle.state.name, "RUNNING")
        asyncio.run(lifecycle.stop())
        self.assertEqual(lifecycle.state.name, "STOPPED")

        transitions = lifecycle.get_transitions()
        states = [t.to_state.name for t in transitions]
        self.assertIn("STARTING", states)
        self.assertIn("RUNNING", states)
        self.assertIn("STOPPING", states)
        self.assertIn("STOPPED", states)

    def test_bootstrap_registry_integrity(self):
        """All registered components are accessible and correct type."""
        from observability.metrics import MetricsCollector
        from observability.alerts import AlertManager
        from observability.health import HealthCheck
        from security.audit import AuditLogger
        from intelligence.decisions import DecisionStore

        bootstrap = SystemBootstrap()
        result = bootstrap.bootstrap()
        registry = result.registry

        # Verify all components are correct types
        self.assertIsInstance(registry.get("metrics"), MetricsCollector)
        self.assertIsInstance(registry.get("alerts"), AlertManager)
        self.assertIsInstance(registry.get("health"), HealthCheck)
        self.assertIsInstance(registry.get("audit"), AuditLogger)
        self.assertIsInstance(registry.get("decision_store"), DecisionStore)

        # Verify registry listing
        names = registry.list_components()
        self.assertIn("metrics", names)
        self.assertIn("alerts", names)
        self.assertIn("health", names)
        self.assertIn("logger", names)
        self.assertIn("audit", names)
        self.assertIn("decision_store", names)
        self.assertIn("feed", names)
        self.assertIn("broker", names)
        self.assertIn("portfolio", names)
        self.assertIn("risk_manager", names)
        self.assertIn("execution_engine", names)

    def test_decision_pipeline_with_bootstrap(self):
        """Decision pipeline can use bootstrapped components."""
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        try:
            from intelligence.decisions import DecisionStore

            bootstrap = SystemBootstrap()
            result = bootstrap.bootstrap()

            registry = result.registry
            store = registry.get("decision_store", DecisionStore)

            # Create pipeline with store
            pipeline = DecisionPipeline(store=store)

            context = PipelineContext(
                symbol="AAPL", price=150.0, timestamp=1700000000.0
            )
            record = pipeline.record_decision(context, "Test decision")

            self.assertEqual(record.market_snapshot.symbol, "AAPL")
            self.assertEqual(pipeline.get_review_status(record.decision_id), "REVIEW_REQUIRED")

            # Export package
            package = pipeline.export_review_package(record.decision_id)
            self.assertIsNotNone(package)
            self.assertEqual(package.decisions[0].market_snapshot.symbol, "AAPL")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_config_driven_bootstrap(self):
        """Bootstrap uses configuration values."""
        os.environ["DATS_INITIAL_CAPITAL"] = "1000000"
        os.environ["DATS_LOG_LEVEL"] = "DEBUG"

        config = ConfigLoader()
        bootstrap = SystemBootstrap(config_loader=config)
        result = bootstrap.bootstrap()

        self.assertTrue(result.success)
        self.assertEqual(bootstrap.config.trading.initial_capital, 1000000.0)
        self.assertEqual(bootstrap.config.monitoring.log_level, "DEBUG")

    def test_bootstrap_failure_rollback(self):
        """Failed bootstrap reports errors without crashing."""
        os.environ["DATS_MAX_LEVERAGE"] = "0.5"  # Invalid: < 1

        config = ConfigLoader()
        bootstrap = SystemBootstrap(config_loader=config)
        result = bootstrap.bootstrap()

        self.assertFalse(result.success)
        self.assertGreater(len(result.errors), 0)
        self.assertIsNone(result.lifecycle)
        self.assertIsNone(result.registry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
