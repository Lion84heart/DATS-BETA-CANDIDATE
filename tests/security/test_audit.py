"""Tests for audit trail logging."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from security.audit import AuditAction, AuditEvent, AuditLogger


class TestAuditLogger(unittest.TestCase):
    """Tests for audit logging."""

    def test_log_event(self):
        """Event logged successfully."""
        logger = AuditLogger()
        event = logger.log(
            action=AuditAction.ORDER_CREATED,
            actor="trader1",
            resource="order-123",
            details={"symbol": "AAPL", "qty": 100},
        )
        self.assertEqual(event.action, AuditAction.ORDER_CREATED)
        self.assertEqual(event.actor, "trader1")
        self.assertEqual(logger.event_count, 1)

    def test_log_with_states(self):
        """Log with before/after states."""
        logger = AuditLogger()
        event = logger.log(
            action=AuditAction.RISK_LIMIT_CHANGED,
            actor="admin",
            resource="risk-config",
            before_state={"max_drawdown": 0.10},
            after_state={"max_drawdown": 0.15},
        )
        self.assertEqual(event.before_state["max_drawdown"], 0.10)
        self.assertEqual(event.after_state["max_drawdown"], 0.15)

    def test_event_hash(self):
        """Event has cryptographic hash."""
        logger = AuditLogger()
        event = logger.log(
            action=AuditAction.LOGIN,
            actor="user1",
            resource="session-1",
        )
        self.assertEqual(len(event.hash), 64)

    def test_chain_integrity(self):
        """Chain integrity verified."""
        logger = AuditLogger()
        logger.log(AuditAction.SYSTEM_START, actor="system", resource="dats")
        logger.log(AuditAction.LOGIN, actor="user1", resource="session-1")
        valid, count = logger.verify_integrity()
        self.assertTrue(valid)
        self.assertEqual(count, 2)

    def test_query_by_action(self):
        """Query filtered by action."""
        logger = AuditLogger()
        logger.log(AuditAction.ORDER_CREATED, actor="t1", resource="o1")
        logger.log(AuditAction.LOGIN, actor="t1", resource="o2")
        events = logger.get_events(action=AuditAction.LOGIN)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, AuditAction.LOGIN)

    def test_query_by_actor(self):
        """Query filtered by actor."""
        logger = AuditLogger()
        logger.log(AuditAction.ORDER_CREATED, actor="alice", resource="o1")
        logger.log(AuditAction.ORDER_CREATED, actor="bob", resource="o2")
        events = logger.get_events(actor="alice")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor, "alice")

    def test_persistence(self):
        """Events persisted to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            path = f.name
        try:
            logger = AuditLogger(persist_path=path)
            logger.log(AuditAction.SYSTEM_START, actor="system", resource="dats")
            content = Path(path).read_text()
            self.assertIn("SYSTEM_START", content)
        finally:
            Path(path).unlink()

    def test_export(self):
        """Export to file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            logger = AuditLogger()
            logger.log(AuditAction.ORDER_CREATED, actor="t1", resource="o1")
            logger.export(path)
            data = __import__("json").loads(Path(path).read_text())
            self.assertEqual(data["count"], 1)
            self.assertEqual(len(data["events"]), 1)
        finally:
            Path(path).unlink()

    def test_to_dict(self):
        """Event converts to dict with all fields."""
        logger = AuditLogger()
        event = logger.log(
            action=AuditAction.KILL_SWITCH_TRIGGERED,
            actor="system",
            resource="portfolio",
            correlation_id="abc-123",
        )
        d = event.to_dict()
        self.assertEqual(d["action"], "KILL_SWITCH_TRIGGERED")
        self.assertEqual(d["correlation_id"], "abc-123")
        self.assertEqual(len(d["hash"]), 64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
