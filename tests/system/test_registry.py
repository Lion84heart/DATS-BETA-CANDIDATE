"""Tests for component registry."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from system.registry import ComponentRegistry


class FakeMetrics:
    pass


class FakeAlerts:
    pass


class TestComponentRegistry(unittest.TestCase):
    """Tests for ComponentRegistry."""

    def test_register_and_get(self):
        """Register and retrieve a component."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        comp = registry.get("metrics")
        self.assertIsInstance(comp, FakeMetrics)

    def test_typed_get(self):
        """Retrieve with type checking."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        comp = registry.get("metrics", FakeMetrics)
        self.assertIsInstance(comp, FakeMetrics)

    def test_typed_get_mismatch(self):
        """Type mismatch raises TypeError."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        with self.assertRaises(TypeError):
            registry.get("metrics", FakeAlerts)

    def test_get_missing(self):
        """Missing component raises KeyError."""
        registry = ComponentRegistry()
        with self.assertRaises(KeyError):
            registry.get("missing")

    def test_has(self):
        """Check component existence."""
        registry = ComponentRegistry()
        self.assertFalse(registry.has("metrics"))
        registry.register("metrics", FakeMetrics())
        self.assertTrue(registry.has("metrics"))

    def test_overwrite(self):
        """Overwrite existing component."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        registry.register("metrics", FakeAlerts())
        comp = registry.get("metrics")
        self.assertIsInstance(comp, FakeAlerts)

    def test_remove(self):
        """Remove a component."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        registry.remove("metrics")
        self.assertFalse(registry.has("metrics"))

    def test_list(self):
        """List all components."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        registry.register("alerts", FakeAlerts())
        names = registry.list_components()
        self.assertEqual(sorted(names), ["alerts", "metrics"])

    def test_clear(self):
        """Clear all components."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        registry.clear()
        self.assertEqual(registry.list_components(), [])

    def test_to_dict(self):
        """Export as dictionary."""
        registry = ComponentRegistry()
        registry.register("metrics", FakeMetrics())
        d = registry.to_dict()
        self.assertEqual(d, {"metrics": "FakeMetrics"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
