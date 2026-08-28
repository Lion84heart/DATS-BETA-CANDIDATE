"""Tests for market data connectors."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from market.connectors.base import ConnectorState, MarketDataConnector, PriceTick
from market.connectors.simulated import SimulatedConnector


class TestPriceTick(unittest.TestCase):
    """Tests for PriceTick dataclass."""

    def test_creation(self):
        """Create a price tick."""
        tick = PriceTick(
            symbol="AAPL",
            timestamp=1700000000.0,
            price=150.0,
            bid=149.9,
            ask=150.1,
            volume=1000.0,
            source="simulated",
        )
        self.assertEqual(tick.symbol, "AAPL")
        self.assertEqual(tick.price, 150.0)
        self.assertEqual(tick.bid, 149.9)
        self.assertEqual(tick.ask, 150.1)

    def test_immutability(self):
        """PriceTick is frozen."""
        tick = PriceTick(symbol="AAPL", timestamp=0.0, price=150.0, bid=149.9, ask=150.1)
        with self.assertRaises(Exception):
            tick.price = 160.0


class TestSimulatedConnector(unittest.TestCase):
    """Tests for SimulatedConnector."""

    def test_initial_state(self):
        """Connector starts disconnected."""
        conn = SimulatedConnector(seed=42)
        self.assertEqual(conn.state, ConnectorState.DISCONNECTED)
        self.assertEqual(conn.name, "simulated")
        self.assertEqual(conn.subscribed_symbols, set())

    def test_configure_symbol(self):
        """Configure symbol initial price."""
        conn = SimulatedConnector(seed=42)
        conn.configure_symbol("AAPL", 150.0)
        self.assertEqual(conn._initial_prices["AAPL"], 150.0)

    def test_is_available(self):
        """Simulated connector is always available."""
        conn = SimulatedConnector()
        self.assertTrue(conn.is_available())

    def test_connect_disconnect(self):
        """Connect and disconnect."""
        async def test():
            conn = SimulatedConnector(seed=42)
            ok = await conn.connect()
            self.assertTrue(ok)
            self.assertEqual(conn.state, ConnectorState.CONNECTED)
            await conn.disconnect()
            self.assertEqual(conn.state, ConnectorState.DISCONNECTED)

        asyncio.run(test())

    def test_subscribe_unsubscribe(self):
        """Subscribe and unsubscribe."""
        async def test():
            conn = SimulatedConnector(seed=42)
            await conn.connect()
            await conn.subscribe(["AAPL", "TSLA"])
            self.assertEqual(conn.subscribed_symbols, {"AAPL", "TSLA"})
            await conn.unsubscribe(["AAPL"])
            self.assertEqual(conn.subscribed_symbols, {"TSLA"})
            await conn.disconnect()

        asyncio.run(test())

    def test_streaming(self):
        """Stream receives ticks."""
        async def test():
            conn = SimulatedConnector(seed=42, tick_interval=0.01)
            conn.configure_symbol("AAPL", 100.0)
            await conn.connect()
            await conn.subscribe(["AAPL"])

            ticks = []
            async for tick in conn.stream():
                ticks.append(tick)
                if len(ticks) >= 3:
                    break

            await conn.disconnect()
            self.assertGreaterEqual(len(ticks), 3)
            self.assertEqual(ticks[0].symbol, "AAPL")
            self.assertEqual(ticks[0].source, "simulated")
            self.assertGreater(ticks[0].price, 0)

        asyncio.run(test())

    def test_callback(self):
        """Callback receives ticks."""
        async def test():
            ticks = []
            conn = SimulatedConnector(seed=42, tick_interval=0.01)
            conn.configure_symbol("AAPL", 100.0)
            conn.add_callback(lambda t: ticks.append(t))
            await conn.connect()
            await conn.subscribe(["AAPL"])
            await asyncio.sleep(0.05)
            await conn.disconnect()
            self.assertGreater(len(ticks), 0)
            self.assertEqual(ticks[0].symbol, "AAPL")

        asyncio.run(test())

    def test_statistics(self):
        """Statistics tracked."""
        async def test():
            conn = SimulatedConnector(seed=42, tick_interval=0.01)
            conn.configure_symbol("AAPL", 100.0)
            await conn.connect()
            await conn.subscribe(["AAPL"])
            await asyncio.sleep(0.05)
            await conn.disconnect()
            stats = conn.statistics
            self.assertGreater(stats.ticks_received, 0)
            self.assertEqual(stats.ticks_dropped, 0)
            self.assertIn("AAPL", stats.symbols)

        asyncio.run(test())

    def test_reset(self):
        """Reset regenerates simulator."""
        conn = SimulatedConnector(seed=42)
        conn.configure_symbol("AAPL", 100.0)
        # After configure, initial_prices has AAPL
        self.assertEqual(conn._initial_prices["AAPL"], 100.0)
        # Reset should re-seed simulator and restore initial prices
        conn.reset()
        self.assertEqual(conn._initial_prices["AAPL"], 100.0)
        self.assertEqual(conn._prices["AAPL"], 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
