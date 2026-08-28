"""Tests for paper trading broker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from market.connectors.base import PriceTick
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperAccount, PaperBroker


class TestPaperAccount(unittest.TestCase):
    """Tests for PaperAccount."""

    def test_initial_state(self):
        """Initial account state."""
        acc = PaperAccount(cash=100000.0, initial_capital=100000.0)
        self.assertEqual(acc.cash, 100000.0)
        self.assertEqual(acc.total_value, 100000.0)
        self.assertEqual(acc.total_pnl, 0.0)
        self.assertEqual(acc.total_return_pct, 0.0)

    def test_with_position(self):
        """Account with position."""
        from trading.execution.broker_base import BrokerPosition

        acc = PaperAccount(cash=50000.0, initial_capital=100000.0)
        acc.positions["AAPL"] = BrokerPosition(
            symbol="AAPL",
            quantity=100.0,
            avg_entry_price=100.0,
            market_price=150.0,
            unrealized_pnl=5000.0,
            realized_pnl=0.0,
        )
        self.assertEqual(acc.total_value, 50000.0 + 100 * 150.0)
        self.assertEqual(acc.total_pnl, acc.total_value - 100000.0)


class TestPaperBroker(unittest.TestCase):
    """Tests for PaperBroker."""

    def test_initial_state(self):
        """Broker initial state."""
        broker = PaperBroker(initial_capital=100000.0)
        self.assertTrue(broker.is_paper)
        self.assertEqual(broker.name, "paper")
        self.assertTrue(broker.is_available())
        self.assertFalse(broker.is_connected)

    def test_connect_disconnect(self):
        """Connect and disconnect."""
        async def test():
            broker = PaperBroker()
            ok = await broker.connect()
            self.assertTrue(ok)
            self.assertTrue(broker.is_connected)
            await broker.disconnect()
            self.assertFalse(broker.is_connected)

        asyncio.run(test())

    def test_price_update(self):
        """Price tick updates position values."""
        broker = PaperBroker(initial_capital=100000.0)
        tick = PriceTick(
            symbol="AAPL",
            timestamp=1700000000.0,
            price=150.0,
            bid=149.9,
            ask=150.1,
            source="simulated",
        )
        broker.on_price_tick(tick)
        self.assertEqual(broker._last_price["AAPL"], 150.0)

    def test_buy_order(self):
        """Buy order simulates fill."""
        async def test():
            broker = PaperBroker(initial_capital=100000.0, commission_per_trade=1.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=100.0,
                    bid=99.9,
                    ask=100.1,
                    source="simulated",
                )
            )
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            result = await broker.submit_order(order)
            self.assertEqual(result.status, "filled")
            self.assertEqual(result.filled_qty, 10.0)
            self.assertGreater(result.avg_fill_price, 0)
            self.assertEqual(result.commission, 1.0)

            # Account updated
            self.assertLess(broker.account.cash, 100000.0)
            self.assertIn("AAPL", broker.account.positions)
            self.assertEqual(broker.account.positions["AAPL"].quantity, 10.0)
            await broker.disconnect()

        asyncio.run(test())

    def test_sell_order(self):
        """Sell order reduces position."""
        async def test():
            broker = PaperBroker(initial_capital=100000.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=100.0,
                    bid=99.9,
                    ask=100.1,
                    source="simulated",
                )
            )
            await broker.connect()

            # Buy first
            buy = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            await broker.submit_order(buy)

            # Then sell
            sell = Order(
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=5.0,
                order_type=OrderType.MARKET,
            )
            result = await broker.submit_order(sell)
            self.assertEqual(result.status, "filled")
            self.assertEqual(broker.account.positions["AAPL"].quantity, 5.0)
            await broker.disconnect()

        asyncio.run(test())

    def test_insufficient_funds(self):
        """Buy rejected if insufficient cash."""
        async def test():
            broker = PaperBroker(initial_capital=100.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=1000.0,
                    bid=999.0,
                    ask=1001.0,
                    source="simulated",
                )
            )
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=100.0,
                order_type=OrderType.MARKET,
            )
            result = await broker.submit_order(order)
            self.assertEqual(result.status, "rejected")
            self.assertIn("Insufficient cash", result.message)
            await broker.disconnect()

        asyncio.run(test())

    def test_no_price_data(self):
        """Order rejected if no price data."""
        async def test():
            broker = PaperBroker()
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            result = await broker.submit_order(order)
            self.assertEqual(result.status, "rejected")
            self.assertIn("No price data", result.message)
            await broker.disconnect()

        asyncio.run(test())

    def test_positions_query(self):
        """Get positions."""
        async def test():
            broker = PaperBroker(initial_capital=100000.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=100.0,
                    bid=99.9,
                    ask=100.1,
                    source="simulated",
                )
            )
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            await broker.submit_order(order)
            positions = await broker.get_positions()
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0].symbol, "AAPL")
            await broker.disconnect()

        asyncio.run(test())

    def test_account_value(self):
        """Get account value."""
        async def test():
            broker = PaperBroker(initial_capital=100000.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=100.0,
                    bid=99.9,
                    ask=100.1,
                    source="simulated",
                )
            )
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            await broker.submit_order(order)
            value = await broker.get_account_value()
            self.assertGreater(value, 0)
            await broker.disconnect()

        asyncio.run(test())

    def test_to_dict(self):
        """Serialize state."""
        broker = PaperBroker(initial_capital=100000.0)
        d = broker.to_dict()
        self.assertEqual(d["name"], "paper")
        self.assertTrue(d["paper_mode"])
        self.assertEqual(d["cash"], 100000.0)

    def test_cancel_order(self):
        """Cancel is always accepted."""
        async def test():
            broker = PaperBroker()
            ok = await broker.cancel_order("any_id")
            self.assertTrue(ok)

        asyncio.run(test())

    def test_sell_without_position(self):
        """Sell without position."""
        async def test():
            broker = PaperBroker(initial_capital=100000.0)
            broker.on_price_tick(
                PriceTick(
                    symbol="AAPL",
                    timestamp=1700000000.0,
                    price=100.0,
                    bid=99.9,
                    ask=100.1,
                    source="simulated",
                )
            )
            await broker.connect()
            order = Order(
                symbol="AAPL",
                side=OrderSide.SELL,
                quantity=10.0,
                order_type=OrderType.MARKET,
            )
            result = await broker.submit_order(order)
            # Should still fill but position will be negative or zero
            self.assertEqual(result.status, "filled")
            await broker.disconnect()

        asyncio.run(test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
