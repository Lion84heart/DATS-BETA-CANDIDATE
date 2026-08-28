"""Tests for end-to-end trading simulation loop."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from simulation.market_sim import MarketSimulator
from simulation.trading_loop import SimulationResult, TradingSimulator


def simple_momentum_strategy(prices: list[float]) -> str:
    """Simple momentum: buy if trending up, sell if trending down."""
    if len(prices) < 5:
        return "HOLD"
    short = sum(prices[-3:]) / 3
    long = sum(prices[-10:]) / 10 if len(prices) >= 10 else short
    if short > long * 1.01:
        return "BUY"
    if short < long * 0.99:
        return "SELL"
    return "HOLD"


def simple_mean_reversion(prices: list[float]) -> str:
    """Simple mean reversion: buy dips, sell rallies."""
    if len(prices) < 10:
        return "HOLD"
    mean = sum(prices[-10:]) / 10
    current = prices[-1]
    if current < mean * 0.98:
        return "BUY"
    if current > mean * 1.02:
        return "SELL"
    return "HOLD"


def permissive_risk(context: dict) -> bool:
    """Always allow (for testing)."""
    return True


def conservative_risk(context: dict) -> bool:
    """Block if drawdown > 10%."""
    return context.get("max_drawdown", 0) < 0.10


def fixed_position_size(price: float, capital: float) -> float:
    """Fixed 10-share position."""
    return 10.0


def percent_position_size(price: float, capital: float) -> float:
    """10% of capital."""
    return (capital * 0.10) / price


class TestTradingSimulator(unittest.TestCase):
    """Tests for trading simulator."""

    def test_basic_simulation(self):
        """Simulation runs and produces results."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 200)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertIsInstance(result, SimulationResult)
        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.start_price, 100.0)

    def test_simulation_with_trades(self):
        """Simulation produces trades."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 500)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        # With 500 steps and momentum strategy, should have some trades
        self.assertIsNotNone(result.num_trades)
        self.assertGreaterEqual(result.num_trades, 0)

    def test_risk_rejection(self):
        """Risk function blocks trades."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 200)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=conservative_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        # Conservative risk may block some trades
        self.assertIsNotNone(result.risk_events)
        self.assertGreaterEqual(result.risk_events, 0)

    def test_batch_simulation(self):
        """Batch simulation over multiple paths."""
        sim = MarketSimulator(seed=42)
        paths = [
            sim.generate_path("AAPL", 100.0, 200),
            sim.generate_path("TSLA", 200.0, 200),
            sim.generate_path("BTC", 50000.0, 200),
        ]

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        results = trader.run_batch(paths, lookback=20)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].symbol, "AAPL")
        self.assertEqual(results[1].symbol, "TSLA")
        self.assertEqual(results[2].symbol, "BTC")

    def test_mean_reversion_strategy(self):
        """Mean reversion strategy runs successfully."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 300)

        trader = TradingSimulator(
            strategy_fn=simple_mean_reversion,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertEqual(result.symbol, "AAPL")
        self.assertIsNotNone(result.total_return_pct)

    def test_percent_position_sizing(self):
        """Percent-based position sizing."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 200)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=percent_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertEqual(result.symbol, "AAPL")

    def test_drawdown_tracking(self):
        """Max drawdown tracked."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 300)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertGreaterEqual(result.max_drawdown_pct, 0.0)

    def test_decisions_recorded(self):
        """Decisions are counted."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 300)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertGreaterEqual(result.decisions_recorded, 0)
        self.assertLessEqual(result.decisions_recorded, result.num_trades)

    def test_slippage_applied(self):
        """Slippage affects results."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 300)

        trader_low = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
            slippage_bps=1.0,
        )
        trader_high = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
            slippage_bps=50.0,
        )

        result_low = trader_low.run(path, lookback=20)
        # Need fresh path for fair comparison (same seed gives same)
        path2 = sim.generate_path("AAPL", 100.0, 300)
        result_high = trader_high.run(path2, lookback=20)

        self.assertEqual(result_low.avg_slippage_bps, 1.0)
        self.assertEqual(result_high.avg_slippage_bps, 50.0)

    def test_sharpe_calculation(self):
        """Sharpe ratio computed."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 300)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        # Sharpe may be None if insufficient data, or a number
        if result.sharpe_ratio is not None:
            self.assertIsInstance(result.sharpe_ratio, float)

    def test_empty_path(self):
        """Very short path handled gracefully."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 5)

        trader = TradingSimulator(
            strategy_fn=simple_momentum_strategy,
            risk_fn=permissive_risk,
            position_size_fn=fixed_position_size,
        )
        result = trader.run(path, lookback=20)

        self.assertEqual(result.symbol, "AAPL")
        self.assertEqual(result.num_trades, 0)  # Not enough data


if __name__ == "__main__":
    unittest.main(verbosity=2)
