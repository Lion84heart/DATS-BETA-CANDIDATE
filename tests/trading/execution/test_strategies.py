"""Tests for execution strategies."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.execution_strategies import IcebergStrategy, TWAPStrategy, VWAPStrategy
from trading.execution.orders import Order, OrderSide, OrderType


class TestTWAPStrategy(unittest.TestCase):
    """Tests for TWAP execution strategy."""

    def test_slice_order(self):
        """TWAP splits into equal slices."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = TWAPStrategy(duration_seconds=300)
        slices = strategy.slice_order(order, num_slices=5)

        self.assertEqual(len(slices), 5)
        self.assertAlmostEqual(slices[0].quantity, 20.0, places=5)
        self.assertEqual(slices[0].delay_seconds, 0.0)
        self.assertEqual(slices[1].delay_seconds, 60.0)
        self.assertEqual(slices[4].delay_seconds, 240.0)

    def test_slice_market_type(self):
        """TWAP slices use market orders."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = TWAPStrategy()
        slices = strategy.slice_order(order, num_slices=3)
        for s in slices:
            self.assertEqual(s.order_type, OrderType.MARKET)

    def test_invalid_duration(self):
        """Zero duration raises error."""
        with self.assertRaises(ValueError):
            TWAPStrategy(duration_seconds=0)


class TestVWAPStrategy(unittest.TestCase):
    """Tests for VWAP execution strategy."""

    def test_slice_order(self):
        """VWAP splits proportionally."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = VWAPStrategy(volume_profile=[2.0, 1.0, 1.0, 1.0, 1.0])
        slices = strategy.slice_order(order, num_slices=5)

        self.assertEqual(len(slices), 5)
        # First slice should be larger (weight 2 vs 1)
        self.assertGreater(slices[0].quantity, slices[1].quantity)
        total = sum(s.quantity for s in slices)
        self.assertAlmostEqual(total, 100.0, places=5)

    def test_default_profile(self):
        """Default profile is equal weighting."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = VWAPStrategy()
        slices = strategy.slice_order(order, num_slices=5)

        for s in slices:
            self.assertAlmostEqual(s.quantity, 20.0, places=5)

    def test_limit_type(self):
        """VWAP uses limit orders."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = VWAPStrategy()
        slices = strategy.slice_order(order)
        for s in slices:
            self.assertEqual(s.order_type, OrderType.LIMIT)


class TestIcebergStrategy(unittest.TestCase):
    """Tests for iceberg execution strategy."""

    def test_visible_quantity(self):
        """Iceberg shows configured visible quantity."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = IcebergStrategy(visible_quantity=20)
        slices = strategy.slice_order(order)

        self.assertEqual(len(slices), 5)
        for s in slices:
            self.assertEqual(s.quantity, 20.0)
            self.assertEqual(s.order_type, OrderType.LIMIT)

    def test_default_visible(self):
        """Default visible is 10% of total."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        strategy = IcebergStrategy()
        slices = strategy.slice_order(order)

        self.assertGreaterEqual(len(slices), 1)
        self.assertEqual(slices[0].quantity, 10.0)

    def test_uneven_quantity(self):
        """Uneven quantity handled correctly."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=25)
        strategy = IcebergStrategy(visible_quantity=10)
        slices = strategy.slice_order(order)

        total = sum(s.quantity for s in slices)
        self.assertAlmostEqual(total, 25.0, places=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
