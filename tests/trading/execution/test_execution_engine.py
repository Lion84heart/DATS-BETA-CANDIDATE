"""Tests for execution engine."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.execution_engine import ExecutionEngine
from trading.execution.fills import FillSimulator
from trading.execution.orders import Order, OrderSide, OrderStatus, OrderType
from trading.execution.slippage import FixedSlippage


class TestExecutionEngine(unittest.TestCase):
    """Tests for execution engine."""

    def setUp(self):
        sim = FillSimulator(
            slippage_model=FixedSlippage(amount=0.001, is_percentage=True),
            fill_probability=1.0,
            partial_fill_enabled=False,
        )
        self.engine = ExecutionEngine(fill_simulator=sim, commission_rate=0.001)

    def test_submit_order(self):
        """Order submission assigns ID."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        self.assertIsNotNone(registered.order_id)
        self.assertEqual(registered.status, OrderStatus.OPEN)

    def test_execute_market_order(self):
        """Market order executes immediately."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        result = asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        self.assertEqual(result.total_filled, 100)
        self.assertEqual(len(result.fills), 1)
        self.assertGreater(result.avg_fill_price, 0)
        self.assertGreater(result.commission, 0)

    def test_execute_limit_order_hit(self):
        """Limit order fills when price is favorable."""
        order = Order(
            symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=100, limit_price=155.0,
        )
        registered = asyncio.run(self.engine.submit(order))
        result = asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        self.assertGreater(result.total_filled, 0)

    def test_execute_limit_order_miss(self):
        """Limit order does not fill when price is unfavorable."""
        order = Order(
            symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=100, limit_price=145.0,
        )
        registered = asyncio.run(self.engine.submit(order))
        result = asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        self.assertEqual(result.total_filled, 0)

    def test_cancel_order(self):
        """Cancel active order."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        cancelled = asyncio.run(self.engine.cancel(registered.order_id))

        self.assertEqual(cancelled.status, OrderStatus.CANCELLED)

    def test_get_active_orders(self):
        """Get active orders."""
        o1 = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        o2 = Order(symbol="TSLA", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=50)
        r1 = asyncio.run(self.engine.submit(o1))
        r2 = asyncio.run(self.engine.submit(o2))

        active = asyncio.run(self.engine.get_active_orders())
        self.assertEqual(len(active), 2)

        asyncio.run(self.engine.cancel(r1.order_id))
        active = asyncio.run(self.engine.get_active_orders())
        self.assertEqual(len(active), 1)

    def test_sell_order_pnl(self):
        """Sell order PnL includes slippage and commission."""
        order = Order(symbol="AAPL", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        result = asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        # Sell at ~149.85 (150 - 0.1% slippage), commission ~14.99
        # PnL = (149.85 - 150.0) * 100 - 14.99 = -15.0 - 14.99 = ~-30
        self.assertAlmostEqual(result.pnl, -30.0, places=0)

    def test_event_callback(self):
        """Event callback fired."""
        events = []
        self.engine.on_event(lambda e, d: events.append((e, d)))

        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        self.assertTrue(any(e == "order_submitted" for e, _ in events))
        self.assertTrue(any(e == "order_filled" for e, _ in events))

    def test_statistics(self):
        """Execution statistics."""
        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=100)
        registered = asyncio.run(self.engine.submit(order))
        asyncio.run(self.engine.execute(registered.order_id, market_price=150.0))

        stats = asyncio.run(self.engine.get_statistics())
        self.assertEqual(stats["total_orders"], 1)
        self.assertEqual(stats["filled_orders"], 1)
        self.assertGreater(stats["total_notional"], 0)
        self.assertGreater(stats["total_commission"], 0)

    def test_unknown_order(self):
        """Execute unknown order raises error."""
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(self.engine.execute("nonexistent", market_price=100.0))
        self.assertIn("not found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
