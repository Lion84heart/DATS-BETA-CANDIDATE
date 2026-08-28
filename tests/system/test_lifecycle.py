"""Tests for system lifecycle management."""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from system.lifecycle import SystemLifecycle, SystemState


class TestSystemLifecycle(unittest.TestCase):
    """Tests for lifecycle management."""

    def test_initial_state(self):
        """System starts in INITIALIZING."""
        lifecycle = SystemLifecycle()
        self.assertEqual(lifecycle.state, SystemState.INITIALIZING)
        self.assertFalse(lifecycle.is_running)

    def test_startup_sequence(self):
        """Startup executes hooks and transitions to RUNNING."""
        lifecycle = SystemLifecycle()
        events = []
        lifecycle.on_startup(lambda: events.append("startup_1"))
        lifecycle.on_startup(lambda: events.append("startup_2"))

        result = asyncio.run(lifecycle.start())

        self.assertTrue(result)
        self.assertEqual(lifecycle.state, SystemState.RUNNING)
        self.assertTrue(lifecycle.is_running)
        self.assertEqual(events, ["startup_1", "startup_2"])

    def test_startup_hook_failure(self):
        """Failed startup hook transitions to ERROR."""
        lifecycle = SystemLifecycle()
        lifecycle.on_startup(lambda: (_ for _ in ()).throw(RuntimeError("fail")))

        result = asyncio.run(lifecycle.start())

        self.assertFalse(result)
        self.assertEqual(lifecycle.state, SystemState.ERROR)

    def test_shutdown_sequence(self):
        """Shutdown executes hooks in reverse order."""
        lifecycle = SystemLifecycle()
        events = []
        lifecycle.on_shutdown(lambda: events.append("shutdown_1"))
        lifecycle.on_shutdown(lambda: events.append("shutdown_2"))

        asyncio.run(lifecycle.start())
        asyncio.run(lifecycle.stop())

        self.assertEqual(lifecycle.state, SystemState.STOPPED)
        self.assertEqual(events, ["shutdown_2", "shutdown_1"])

    def test_shutdown_idempotent(self):
        """Shutdown is idempotent."""
        lifecycle = SystemLifecycle()
        asyncio.run(lifecycle.start())
        asyncio.run(lifecycle.stop())
        asyncio.run(lifecycle.stop())  # Should not raise
        self.assertEqual(lifecycle.state, SystemState.STOPPED)

    def test_request_shutdown(self):
        """Request shutdown sets flag."""
        lifecycle = SystemLifecycle()
        lifecycle.request_shutdown("test reason")
        self.assertTrue(lifecycle.is_shutting_down)
        self.assertEqual(lifecycle.state, SystemState.STOPPING)

    def test_signal_handlers_installed(self):
        """Signal handlers can be installed."""
        lifecycle = SystemLifecycle()
        lifecycle.install_signal_handlers()
        # Just verify no exception
        self.assertTrue(True)

    def test_transition_tracking(self):
        """Transitions are recorded."""
        lifecycle = SystemLifecycle()
        lifecycle.transition(SystemState.STARTING, "test")
        lifecycle.transition(SystemState.RUNNING, "test2")
        transitions = lifecycle.get_transitions()
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0].to_state, SystemState.STARTING)
        self.assertEqual(transitions[1].to_state, SystemState.RUNNING)

    def test_uptime_tracking(self):
        """Uptime tracked after start."""
        lifecycle = SystemLifecycle()
        self.assertEqual(lifecycle.uptime_seconds, 0.0)
        asyncio.run(lifecycle.start())
        self.assertGreater(lifecycle.uptime_seconds, 0)

    def test_to_dict(self):
        """Serialization works."""
        lifecycle = SystemLifecycle()
        asyncio.run(lifecycle.start())
        d = lifecycle.to_dict()
        self.assertEqual(d["state"], "RUNNING")
        self.assertIn("uptime_seconds", d)
        self.assertIn("transitions", d)

    def test_degraded_mode(self):
        """Degraded mode transition."""
        lifecycle = SystemLifecycle()
        events = []
        lifecycle.on_degraded(lambda: events.append("degraded"))
        lifecycle.transition(SystemState.DEGRADED, "health check failed")
        self.assertEqual(lifecycle.state, SystemState.DEGRADED)
        self.assertTrue(lifecycle.is_running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
