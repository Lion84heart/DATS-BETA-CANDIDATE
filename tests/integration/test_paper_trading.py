"""Integration tests for paper trading mode."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.paper_trading import PaperTradingConfig, PaperTradingMode


def simple_momentum(prices: list[float]) -> str:
    """Simple momentum strategy for testing."""
    if len(prices) < 5:
        return "HOLD"
    short = sum(prices[-5:]) / 5
    long = sum(prices[-10:]) / 10
    if short > long * 1.01:
        return "BUY"
    if short < long * 0.99:
        return "SELL"
    return "HOLD"


def always_pass(context: dict) -> bool:
    """Always pass risk check."""
    return True


def fixed_size(price: float, cash: float) -> float:
    """Fixed position size."""
    return 1.0


class TestPaperTradingMode(unittest.TestCase):
    """Integration tests for paper trading mode."""

    def test_initial_state(self):
        """Paper trading mode initial state."""
        config = PaperTradingConfig(
            symbols=["AAPL"],
            strategy_fn=simple_momentum,
            risk_fn=always_pass,
            position_size_fn=fixed_size,
        )
        mode = PaperTradingMode(config)
        self.assertFalse(mode._running)
        self.assertEqual(mode.config.symbols, ["AAPL"])

    def test_start_stop(self):
        """Start and stop paper trading."""
        async def test():
            config = PaperTradingConfig(
                symbols=["AAPL"],
                strategy_fn=simple_momentum,
                risk_fn=always_pass,
                position_size_fn=fixed_size,
                tick_interval=0.01,
                lookback=5,
            )
            mode = PaperTradingMode(config)
            ok = await mode.start()
            self.assertTrue(ok)
            self.assertTrue(mode._running)
            await asyncio.sleep(0.05)  # Let some ticks flow
            await mode.stop()
            self.assertFalse(mode._running)

        asyncio.run(test())

    def test_trading_generates_ticks(self):
        """Trading generates price ticks."""
        async def test():
            config = PaperTradingConfig(
                symbols=["AAPL"],
                strategy_fn=simple_momentum,
                risk_fn=always_pass,
                position_size_fn=fixed_size,
                tick_interval=0.01,
                lookback=5,
            )
            mode = PaperTradingMode(config)
            await mode.start()
            await asyncio.sleep(0.1)  # Generate ticks
            await mode.stop()

            # Should have collected price history
            self.assertIn("AAPL", mode._price_history)
            self.assertGreater(len(mode._price_history["AAPL"]), 0)

        asyncio.run(test())

    def test_account_summary(self):
        """Account summary after trading."""
        async def test():
            config = PaperTradingConfig(
                symbols=["AAPL"],
                strategy_fn=simple_momentum,
                risk_fn=always_pass,
                position_size_fn=fixed_size,
                tick_interval=0.01,
                lookback=5,
            )
            mode = PaperTradingMode(config)
            await mode.start()
            await asyncio.sleep(0.1)
            await mode.stop()

            summary = mode.get_account_summary()
            self.assertIn("cash", summary)
            self.assertIn("total_value", summary)
            self.assertIn("positions", summary)
            self.assertIn("symbols", summary)
            self.assertEqual(summary["symbols"], ["AAPL"])

        asyncio.run(test())

    def test_to_dict(self):
        """Serialize paper trading state."""
        async def test():
            config = PaperTradingConfig(
                symbols=["AAPL"],
                strategy_fn=simple_momentum,
                risk_fn=always_pass,
                position_size_fn=fixed_size,
                tick_interval=0.01,
                lookback=5,
            )
            mode = PaperTradingMode(config)
            await mode.start()
            await asyncio.sleep(0.05)
            await mode.stop()

            d = mode.to_dict()
            self.assertIn("running", d)
            self.assertIn("config", d)
            self.assertIn("account", d)
            self.assertIn("broker", d)
            self.assertIn("feed", d)
            self.assertFalse(d["running"])

        asyncio.run(test())

    def test_multiple_symbols(self):
        """Trade multiple symbols."""
        async def test():
            config = PaperTradingConfig(
                symbols=["AAPL", "TSLA"],
                strategy_fn=simple_momentum,
                risk_fn=always_pass,
                position_size_fn=fixed_size,
                tick_interval=0.01,
                lookback=5,
            )
            mode = PaperTradingMode(config)
            await mode.start()
            await asyncio.sleep(0.1)
            await mode.stop()

            self.assertIn("AAPL", mode._price_history)
            self.assertIn("TSLA", mode._price_history)

        asyncio.run(test())

    def test_decision_recording(self):
        """Decisions recorded during paper trading."""
        async def test():
            from system.decision_pipeline import DecisionPipeline
            from intelligence.decisions import DecisionStore
            import tempfile
            import shutil

            temp_dir = tempfile.mkdtemp()
            try:
                store = DecisionStore(data_dir=temp_dir)
                pipeline = DecisionPipeline(store=store)

                config = PaperTradingConfig(
                    symbols=["AAPL"],
                    strategy_fn=simple_momentum,
                    risk_fn=always_pass,
                    position_size_fn=fixed_size,
                    tick_interval=0.01,
                    lookback=5,
                )
                mode = PaperTradingMode(config, pipeline=pipeline)
                await mode.start()
                await asyncio.sleep(0.1)
                await mode.stop()

                # Should have recorded some decisions
                summary = pipeline.get_summary()
                self.assertGreater(summary["total_decisions_recorded"], 0)
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        asyncio.run(test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
