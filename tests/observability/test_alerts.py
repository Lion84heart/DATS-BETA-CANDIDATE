"""Tests for alert management."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from observability.alerts import (  # type: ignore
    AlertEvent,
    AlertManager,
    AlertRule,
    AlertSeverity,
    AlertState,
)


class TestAlertManager(unittest.TestCase):
    """Tests for alert management."""

    def test_default_rules_loaded(self):
        """22 default rules loaded."""
        mgr = AlertManager()
        self.assertEqual(mgr.rule_count, 22)

    def test_greater_than_trigger(self):
        """Greater-than condition fires correctly."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        events = mgr.evaluate("cpu", 85.0)
        self.assertTrue(any(e.rule_name == "cpu_high" for e in events))

    def test_less_than_trigger(self):
        """Less-than condition fires correctly."""
        rule = AlertRule(
            name="fill_low", description="Fill low", severity=AlertSeverity.MEDIUM,
            metric_name="fill", condition="<", threshold=0.70, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        events = mgr.evaluate("fill", 0.60)
        self.assertTrue(any(e.rule_name == "fill_low" for e in events))

    def test_equals_trigger(self):
        """Equals condition fires correctly."""
        rule = AlertRule(
            name="disconnected", description="Feed down", severity=AlertSeverity.CRITICAL,
            metric_name="feed", condition="==", threshold=0.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        events = mgr.evaluate("feed", 0.0)
        self.assertTrue(any(e.rule_name == "disconnected" for e in events))

    def test_no_trigger_when_ok(self):
        """No event when value is OK."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        events = mgr.evaluate("cpu", 50.0)
        self.assertEqual(len(events), 0)

    def test_cooldown_prevents_duplicate(self):
        """Cooldown prevents immediate re-firing."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
            cooldown_seconds=300,
        )
        mgr = AlertManager(rules=[rule])
        mgr.evaluate("cpu", 85.0)
        events = mgr.evaluate("cpu", 85.0)
        self.assertEqual(len(events), 0)

    def test_auto_resolve(self):
        """Alert resolves when value returns to normal."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        # Fire first
        mgr.evaluate("cpu", 85.0)
        # Now resolve
        events = mgr.evaluate("cpu", 50.0)
        self.assertTrue(any(e.state == AlertState.RESOLVED for e in events))

    def test_get_active_alerts(self):
        """Get currently firing alerts."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.evaluate("cpu", 85.0)
        active = mgr.get_active_alerts()
        self.assertGreater(len(active), 0)
        self.assertEqual(active[0].rule_name, "cpu_high")

    def test_get_alert_history(self):
        """Alert history retrieval."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.evaluate("cpu", 85.0)
        history = mgr.get_alert_history(rule_name="cpu_high")
        self.assertGreater(len(history), 0)

    def test_filter_by_severity(self):
        """Filter history by severity."""
        rule = AlertRule(
            name="drawdown", description="Drawdown", severity=AlertSeverity.CRITICAL,
            metric_name="dd", condition=">", threshold=0.10, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.evaluate("dd", 0.15)
        critical = mgr.get_alert_history(severity=AlertSeverity.CRITICAL)
        self.assertTrue(any(e.rule_name == "drawdown" for e in critical))

    def test_suppress(self):
        """Suppress alert rule."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.suppress("cpu_high")
        events = mgr.evaluate("cpu", 85.0)
        self.assertEqual(len(events), 0)

    def test_unsuppress(self):
        """Unsuppress alert rule."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.suppress("cpu_high")
        mgr.unsuppress("cpu_high")
        events = mgr.evaluate("cpu", 85.0)
        self.assertTrue(any(e.rule_name == "cpu_high" for e in events))

    def test_duration_breached(self):
        """Alert fires only after duration exceeded."""
        rule = AlertRule(
            name="slow_query",
            description="DB query slow",
            severity=AlertSeverity.MEDIUM,
            metric_name="db.latency",
            condition=">",
            threshold=100.0,
            duration_seconds=0.1,
        )
        mgr = AlertManager(rules=[rule])
        # First evaluation shouldn't fire (within duration)
        events = mgr.evaluate("db.latency", 200.0)
        self.assertEqual(len(events), 0)
        # Wait for duration
        time.sleep(0.15)
        events = mgr.evaluate("db.latency", 200.0)
        self.assertTrue(any(e.rule_name == "slow_query" for e in events))

    def test_callback(self):
        """Alert callback fired."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        events = []
        mgr.on_alert(lambda e: events.append(e.rule_name))
        mgr.evaluate("cpu", 85.0)
        self.assertEqual(events, ["cpu_high"])

    def test_firing_count(self):
        """Count of firing alerts."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        self.assertEqual(mgr.get_firing_count(), 0)
        mgr.evaluate("cpu", 85.0)
        self.assertGreaterEqual(mgr.get_firing_count(), 1)

    def test_clear_history(self):
        """Clear alert history."""
        rule = AlertRule(
            name="cpu_high", description="CPU high", severity=AlertSeverity.HIGH,
            metric_name="cpu", condition=">", threshold=80.0, duration_seconds=0,
        )
        mgr = AlertManager(rules=[rule])
        mgr.evaluate("cpu", 85.0)
        mgr.clear_history()
        self.assertEqual(len(mgr.get_alert_history()), 0)

    def test_status(self):
        """Get alert rule status."""
        mgr = AlertManager()
        status = mgr.get_status()
        self.assertIn("cpu_usage_high", status)
        self.assertEqual(status["cpu_usage_high"], AlertState.OK)

    def test_all_critical_alerts(self):
        """Verify all critical alerts are configured."""
        mgr = AlertManager()
        critical = [r for r in mgr.rules.values() if r.severity == AlertSeverity.CRITICAL]
        self.assertEqual(len(critical), 4)  # drawdown, daily loss, feed, kill switch


if __name__ == "__main__":
    unittest.main(verbosity=2)
