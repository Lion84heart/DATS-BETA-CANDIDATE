"""Tests for order types and order book."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.orders import Order, OrderSide, OrderStatus, OrderType


class TestOrderCreation(unittest.TestCase):
    """Tests for Order creation and validation."""

    def test_market_order(self):
        """Create a basic market order."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        self.assertEqual(order.symbol, "AAPL")
        self.assertEqual(order.side, OrderSide.BUY)
        self.assertEqual(order.order_type, OrderType.MARKET)
        self.assertEqual(order.quantity, 100)
        self.assertEqual(order.status, OrderStatus.PENDING)
        self.assertEqual(order.remaining_quantity, 100)

    def test_limit_order(self):
        """Create a limit order."""
        order = Order(
            symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.LIMIT,
            quantity=50, limit_price=150.0,
        )
        self.assertEqual(order.limit_price, 150.0)
        # Freshly created order is PENDING, not active until opened
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_stop_order(self):
        """Create a stop order."""
        order = Order(
            symbol="TSLA", side=OrderSide.BUY, order_type=OrderType.STOP,
            quantity=10, stop_price=200.0,
        )
        self.assertEqual(order.stop_price, 200.0)

    def test_stop_limit_order(self):
        """Create a stop-limit order."""
        order = Order(
            symbol="GOOGL", side=OrderSide.SELL, order_type=OrderType.STOP_LIMIT,
            quantity=5, stop_price=100.0, limit_price=99.5,
        )
        self.assertEqual(order.stop_price, 100.0)
        self.assertEqual(order.limit_price, 99.5)

    def test_trailing_stop_order(self):
        """Create a trailing stop order."""
        order = Order(
            symbol="MSFT", side=OrderSide.SELL, order_type=OrderType.TRAILING_STOP,
            quantity=20, trailing_distance=0.05, trailing_type="percent",
        )
        self.assertEqual(order.trailing_distance, 0.05)
        self.assertEqual(order.trailing_type, "percent")

    def test_invalid_quantity(self):
        """Negative quantity raises error."""
        with self.assertRaises(ValueError):
            Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=-1)

    def test_limit_requires_price(self):
        """Limit order without price raises error."""
        with self.assertRaises(ValueError):
            Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=10)

    def test_stop_requires_price(self):
        """Stop order without price raises error."""
        with self.assertRaises(ValueError):
            Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.STOP, quantity=10)

    def test_trailing_requires_distance(self):
        """Trailing stop without distance raises error."""
        with self.assertRaises(ValueError):
            Order(symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.TRAILING_STOP, quantity=10)


class TestOrderFill(unittest.TestCase):
    """Tests for order fill operations."""

    def test_partial_fill(self):
        """Partial fill updates state correctly."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        updated = order.with_fill(30, 150.0)
        self.assertEqual(updated.filled_quantity, 30)
        self.assertEqual(updated.remaining_quantity, 70)
        self.assertEqual(updated.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(updated.fill_percent, 30.0)

    def test_full_fill(self):
        """Full fill sets status to FILLED."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        updated = order.with_fill(100, 150.0)
        self.assertEqual(updated.status, OrderStatus.FILLED)
        self.assertEqual(updated.remaining_quantity, 0)
        self.assertTrue(updated.is_complete)

    def test_overfill_protection(self):
        """Cannot fill more than quantity."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        with self.assertRaises(ValueError):
            order.with_fill(101, 150.0)

    def test_fill_metadata(self):
        """Fill adds metadata."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        updated = order.with_fill(50, 150.0)
        self.assertIn("avg_fill_price", updated.metadata)
        self.assertIn("last_fill_qty", updated.metadata)


class TestOrderStatus(unittest.TestCase):
    """Tests for status transitions."""

    def test_cancel_order(self):
        """Cancel sets correct status."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        cancelled = order.with_status(OrderStatus.CANCELLED, "User request")
        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)
        self.assertTrue(cancelled.is_complete)
        self.assertFalse(cancelled.is_active)

    def test_reject_order(self):
        """Reject sets correct status."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        rejected = order.with_status(OrderStatus.REJECTED, "Insufficient funds")
        self.assertEqual(rejected.status, OrderStatus.REJECTED)

    def test_serialization(self):
        """Order can be serialized to dict."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        d = order.to_dict()
        self.assertEqual(d["symbol"], "AAPL")
        self.assertEqual(d["side"], "BUY")
        self.assertEqual(d["quantity"], 100)
        self.assertIn("remaining_quantity", d)
        self.assertIn("is_active", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
