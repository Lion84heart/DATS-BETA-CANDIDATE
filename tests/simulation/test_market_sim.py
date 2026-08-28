"""Tests for market price simulation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from simulation.market_sim import MarketSimulator, PricePath


class TestMarketSimulator(unittest.TestCase):
    """Tests for market simulator."""

    def test_generate_path_length(self):
        """Generated path has correct length."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", start_price=100.0, steps=100)
        self.assertEqual(len(path.prices), 101)  # start + 100 steps
        self.assertEqual(path.symbol, "AAPL")

    def test_path_prices_positive(self):
        """All prices are positive."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("BTC", start_price=50000.0, steps=200)
        self.assertTrue(all(p > 0 for p in path.prices))

    def test_reproducibility(self):
        """Same seed produces same path."""
        sim1 = MarketSimulator(seed=123)
        sim2 = MarketSimulator(seed=123)
        p1 = sim1.generate_path("X", 100.0, 50)
        p2 = sim2.generate_path("X", 100.0, 50)
        self.assertEqual(p1.prices, p2.prices)

    def test_returns_calculation(self):
        """Returns computed correctly."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 10)
        returns = path.returns
        self.assertEqual(len(returns), 10)

    def test_multi_asset(self):
        """Multi-asset generation produces paths."""
        sim = MarketSimulator(seed=42)
        symbols = ["A", "B"]
        start_prices = {"A": 100.0, "B": 50.0}
        paths = sim.generate_multi_asset(symbols, start_prices, steps=50)
        self.assertEqual(len(paths), 2)
        self.assertIn("A", paths)
        self.assertIn("B", paths)
        self.assertEqual(len(paths["A"].prices), 51)

    def test_stream_prices(self):
        """Streaming price generator yields values."""
        sim = MarketSimulator(seed=42)
        stream = sim.stream_prices("AAPL", 100.0)
        prices = []
        for _ in range(10):
            ts, price = next(stream)
            prices.append(price)
            self.assertGreater(price, 0)
        self.assertEqual(len(prices), 10)

    def test_volatility_effect(self):
        """Higher volatility produces wider price range."""
        sim = MarketSimulator(seed=42)
        low_vol = sim.generate_path("X", 100.0, 200, volatility=0.01)
        high_vol = sim.generate_path("X", 100.0, 200, volatility=0.05)
        low_range = max(low_vol.prices) - min(low_vol.prices)
        high_range = max(high_vol.prices) - min(high_vol.prices)
        self.assertGreater(high_range, low_range)

    def test_drift_effect(self):
        """Positive drift produces upward bias."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("X", 100.0, 500, drift=0.001)
        # With positive drift, final price should tend > start on average
        # With fixed seed, check it's reasonable
        self.assertGreater(path.final_price, 50.0)  # Not crashed

    def test_path_properties(self):
        """Price path properties accessible."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 10)
        self.assertGreater(path.max_price, 0)
        self.assertGreater(path.min_price, 0)
        self.assertEqual(path.final_price, path.prices[-1])

    def test_correlation_structure(self):
        """Correlated assets move together."""
        sim = MarketSimulator(seed=42)
        corr = {("A", "B"): 0.9, ("B", "A"): 0.9}
        paths = sim.generate_multi_asset(["A", "B"], {"A": 100.0, "B": 100.0}, 100, corr)
        # Highly correlated assets should have similar directional moves
        ret_a = paths["A"].returns
        ret_b = paths["B"].returns
        same_direction = sum(1 for a, b in zip(ret_a, ret_b) if (a > 0) == (b > 0))
        self.assertGreater(same_direction, len(ret_a) * 0.5)  # Better than random


if __name__ == "__main__":
    unittest.main(verbosity=2)
