"""Tests for order lifecycle state machine."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.order_lifecycle import OrderLifecycleManager
from trading.execution.orders import Order, OrderSide, OrderStatus, OrderType


class TestOrderLifecycle(unittest.TestCase):
    """Tests for order lifecycle manager."""

    def setUp(self):
        self.manager = OrderLifecycleManager()

    def test_register_order(self):
        """Order registration assigns ID."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        self.assertIsNotNone(registered.order_id)
        self.assertGreater(len(registered.order_id), 0)

    def test_valid_transition(self):
        """Valid state transition succeeds."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.OPEN))

        updated = asyncio.run(self.manager.get(registered.order_id))
        self.assertEqual(updated.status, OrderStatus.OPEN)

    def test_invalid_transition(self):
        """Invalid state transition raises error."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))

        with self.assertRaises(ValueError) as ctx:
            asyncio.run(self.manager.transition(registered.order_id, OrderStatus.FILLED))
        self.assertIn("Invalid transition", str(ctx.exception))

    def test_fill_updates_state(self):
        """Fill updates order state."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.OPEN))

        asyncio.run(self.manager.fill(registered.order_id, 50, 150.0))
        updated = asyncio.run(self.manager.get(registered.order_id))
        self.assertEqual(updated.filled_quantity, 50)
        self.assertEqual(updated.status, OrderStatus.PARTIALLY_FILLED)

    def test_fill_to_completion(self):
        """Fill reaches completion."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.OPEN))

        asyncio.run(self.manager.fill(registered.order_id, 100, 150.0))
        updated = asyncio.run(self.manager.get(registered.order_id))
        self.assertEqual(updated.status, OrderStatus.FILLED)
        self.assertTrue(updated.is_complete)

    def test_cancel_order(self):
        """Cancel active order."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.OPEN))

        asyncio.run(self.manager.cancel(registered.order_id))
        updated = asyncio.run(self.manager.get(registered.order_id))
        self.assertEqual(updated.status, OrderStatus.CANCELLED)

    def test_get_active(self):
        """Get active orders."""
        o1 = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        o2 = Order(symbol="TSLA", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=50)
        r1 = asyncio.run(self.manager.register(o1))
        r2 = asyncio.run(self.manager.register(o2))
        asyncio.run(self.manager.transition(r1.order_id, OrderStatus.OPEN))
        asyncio.run(self.manager.transition(r2.order_id, OrderStatus.OPEN))

        active = asyncio.run(self.manager.get_active())
        self.assertEqual(len(active), 2)

        asyncio.run(self.manager.cancel(r1.order_id))
        active = asyncio.run(self.manager.get_active())
        self.assertEqual(len(active), 1)

    def test_callback(self):
        """Transition callback fired."""
        events = []
        self.manager.on_transition(lambda old, new: events.append((old.status, new.status)))

        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.OPEN))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], (OrderStatus.PENDING, OrderStatus.OPEN))

    def test_reject_order(self):
        """Reject pending order."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.manager.register(order))
        asyncio.run(self.manager.transition(registered.order_id, OrderStatus.REJECTED, "Risk limit"))

        updated = asyncio.run(self.manager.get(registered.order_id))
        self.assertEqual(updated.status, OrderStatus.REJECTED)
        self.assertIn("Risk limit", updated.metadata.get("status_reason", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
