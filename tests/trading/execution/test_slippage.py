"""Tests for slippage models."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.execution.slippage import FixedSlippage, RandomSlippage, VolatilitySlippage


class TestFixedSlippage(unittest.TestCase):
    """Tests for fixed slippage model."""

    def test_dollar_slippage(self):
        """Fixed dollar slippage."""
        model = FixedSlippage(amount=0.05, is_percentage=False)
        slip = model.estimate_slippage(expected_price=100.0, quantity=10, side="BUY")
        self.assertEqual(slip, 0.05)

    def test_percentage_slippage(self):
        """Fixed percentage slippage."""
        model = FixedSlippage(amount=0.001, is_percentage=True)
        slip = model.estimate_slippage(expected_price=100.0, quantity=10, side="BUY")
        self.assertEqual(slip, 0.10)  # 0.1% of 100

    def test_side_independence(self):
        """Fixed slippage is same for buy/sell."""
        model = FixedSlippage(amount=0.05)
        buy_slip = model.estimate_slippage(100.0, 10, "BUY")
        sell_slip = model.estimate_slippage(100.0, 10, "SELL")
        self.assertEqual(buy_slip, sell_slip)


class TestVolatilitySlippage(unittest.TestCase):
    """Tests for volatility slippage model."""

    def test_base_slippage(self):
        """Base slippage without extra factors."""
        model = VolatilitySlippage(base_bps=5.0)
        slip = model.estimate_slippage(expected_price=100.0, quantity=10, side="BUY")
        self.assertEqual(slip, 100.0 * 0.0005)  # 5 bps

    def test_volatility_component(self):
        """Higher volatility = higher slippage."""
        model = VolatilitySlippage(base_bps=5.0, vol_multiplier=10.0)
        slip_low = model.estimate_slippage(100.0, 10, "BUY", volatility=0.10)
        slip_high = model.estimate_slippage(100.0, 10, "BUY", volatility=0.30)
        self.assertGreater(slip_high, slip_low)

    def test_size_component(self):
        """Larger relative order = higher slippage."""
        model = VolatilitySlippage(base_bps=5.0, size_multiplier=50.0)
        slip_small = model.estimate_slippage(100.0, 10, "BUY", volume=1000)
        slip_large = model.estimate_slippage(100.0, 500, "BUY", volume=1000)
        self.assertGreater(slip_large, slip_small)

    def test_all_components(self):
        """Slippage with all components."""
        model = VolatilitySlippage(base_bps=5.0, vol_multiplier=10.0, size_multiplier=50.0)
        slip = model.estimate_slippage(
            expected_price=100.0, quantity=100, side="BUY",
            volatility=0.20, volume=1000,
        )
        # 5 bps base + (0.20 * 10) bps + (100/1000 * 50) bps
        # = 5 + 2 + 5 = 12 bps = 0.12%
        expected = 100.0 * (12.0 / 10000.0)
        self.assertAlmostEqual(slip, expected, places=2)


class TestRandomSlippage(unittest.TestCase):
    """Tests for random slippage model."""

    def test_range(self):
        """Slippage falls within configured range."""
        model = RandomSlippage(min_bps=1.0, max_bps=10.0)
        for _ in range(100):
            slip = model.estimate_slippage(100.0, 10, "BUY")
            self.assertGreaterEqual(slip, 100.0 * 0.0001)  # 1 bps
            self.assertLessEqual(slip, 100.0 * 0.001)  # 10 bps

    def test_variation(self):
        """Random slippage varies between calls."""
        model = RandomSlippage(min_bps=1.0, max_bps=10.0)
        slips = [model.estimate_slippage(100.0, 10, "BUY") for _ in range(10)]
        self.assertGreater(len(set(round(s, 6) for s in slips)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
