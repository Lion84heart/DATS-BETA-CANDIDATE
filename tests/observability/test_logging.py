"""Tests for structured logging."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import logging
import unittest

from observability.logging import JSONFormatter, StructuredLogger  # type: ignore


class TestStructuredLogger(unittest.TestCase):
    """Tests for structured logger."""

    def setUp(self):
        self.output = StringIO()
        handler = logging.StreamHandler(self.output)
        handler.setFormatter(JSONFormatter())
        self.logger = StructuredLogger("test")
        self.logger._logger.handlers = [handler]
        self.logger._logger.propagate = False

    def test_info_log(self):
        """Info log produces JSON with message."""
        self.logger.info("Test message", key="value")
        output = self.output.getvalue().strip()
        self.assertTrue(output)
        entry = json.loads(output)
        self.assertEqual(entry["message"], "Test message")
        self.assertEqual(entry["level"], "INFO")
        self.assertEqual(entry["key"], "value")

    def test_error_log(self):
        """Error log has ERROR level."""
        self.logger.error("Error occurred")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertEqual(entry["level"], "ERROR")

    def test_event_log(self):
        """Event log includes event_type."""
        self.logger.event("order.submitted", "Order created", order_id="123")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertEqual(entry["event_type"], "order.submitted")
        self.assertEqual(entry["order_id"], "123")

    def test_correlation_id(self):
        """Correlation ID propagated in logs."""
        StructuredLogger.set_correlation_id("abc-123")
        self.logger.info("With correlation")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertEqual(entry["correlation_id"], "abc-123")

    def test_trace_context(self):
        """Trace context propagated."""
        StructuredLogger.set_trace_context("trace-1", "span-1")
        self.logger.info("With trace")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertEqual(entry["trace_id"], "trace-1")
        self.assertEqual(entry["span_id"], "span-1")

    def test_clear_context(self):
        """Clear context removes IDs."""
        StructuredLogger.set_correlation_id("abc")
        StructuredLogger.clear_context()
        self.logger.info("After clear")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertIsNone(entry["correlation_id"])

    def test_get_correlation_id(self):
        """Get correlation ID returns current value."""
        StructuredLogger.set_correlation_id("test-id")
        self.assertEqual(StructuredLogger.get_correlation_id(), "test-id")

    def test_source_info(self):
        """Log entry includes source file info."""
        self.logger.info("Source test")
        output = self.output.getvalue().strip()
        entry = json.loads(output)
        self.assertIn("source", entry)
        self.assertIn("file", entry["source"])

    def tearDown(self):
        StructuredLogger.clear_context()


if __name__ == "__main__":
    unittest.main(verbosity=2)
