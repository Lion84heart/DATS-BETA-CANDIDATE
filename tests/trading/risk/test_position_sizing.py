"""Tests for position sizing algorithms."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

import numpy as np

from trading.risk.position_sizing import KellyCriterion, PositionSizer, VolatilitySizer


class TestKellyCriterion(unittest.TestCase):
    """Tests for Kelly Criterion position sizing."""

    def test_basic_kelly(self):
        """Kelly with 60% win rate, 2:1 reward/risk."""
        kelly = KellyCriterion(fraction=1.0, max_risk_per_trade=1.0)
        result = kelly.calculate(
            capital=100000,
            win_rate=0.6,
            avg_win=200,
            avg_loss=100,
            current_price=50.0,
        )
        # f* = (0.6 * 2 - 0.4) / 2 = 0.4
        self.assertAlmostEqual(result.risk_fraction, 0.4, places=5)
        self.assertAlmostEqual(result.recommended_size, 800.0, places=1)  # 100k * 0.4 / 50

    def test_half_kelly(self):
        """Half-Kelly reduces position size."""
        kelly = KellyCriterion(fraction=0.5, max_risk_per_trade=1.0)
        result = kelly.calculate(
            capital=100000,
            win_rate=0.6,
            avg_win=200,
            avg_loss=100,
            current_price=50.0,
        )
        # Half of 0.4 = 0.2
        self.assertAlmostEqual(result.risk_fraction, 0.2, places=5)

    def test_max_risk_cap(self):
        """Position size capped at max_risk_per_trade."""
        kelly = KellyCriterion(fraction=1.0, max_risk_per_trade=0.02)
        result = kelly.calculate(
            capital=100000,
            win_rate=0.8,
            avg_win=500,
            avg_loss=100,
            current_price=50.0,
        )
        # Raw Kelly would be high, but capped at 2%
        self.assertLessEqual(result.risk_fraction, 0.02)
        self.assertLessEqual(result.recommended_size, 40.0)  # 100k * 0.02 / 50

    def test_negative_edge(self):
        """Kelly returns 0 when edge is negative."""
        kelly = KellyCriterion(fraction=1.0)
        result = kelly.calculate(
            capital=100000,
            win_rate=0.3,
            avg_win=100,
            avg_loss=100,
            current_price=50.0,
        )
        self.assertEqual(result.risk_fraction, 0.0)
        self.assertEqual(result.recommended_size, 0.0)

    def test_optimal_fraction(self):
        """Optimal fraction calculation."""
        kelly = KellyCriterion()
        f = kelly.optimal_fraction(win_rate=0.6, avg_win=200, avg_loss=100)
        self.assertAlmostEqual(f, 0.4, places=5)

    def test_invalid_fraction(self):
        """Invalid fraction raises error."""
        with self.assertRaises(ValueError):
            KellyCriterion(fraction=0.0)
        with self.assertRaises(ValueError):
            KellyCriterion(fraction=1.5)

    def test_invalid_capital(self):
        """Invalid capital raises error."""
        kelly = KellyCriterion()
        with self.assertRaises(ValueError):
            kelly.calculate(capital=0, win_rate=0.5, avg_win=100, avg_loss=100, current_price=50)


class TestVolatilitySizer(unittest.TestCase):
    """Tests for volatility-based position sizing."""

    def test_basic_volatility_sizing(self):
        """Position size inversely proportional to volatility."""
        sizer = VolatilitySizer(target_volatility=0.15, max_risk_per_trade=0.02)
        result = sizer.calculate(
            capital=100000,
            win_rate=0.5,
            avg_win=100,
            avg_loss=100,
            current_price=50.0,
            volatility=0.30,  # 2x target
        )
        # vol_ratio = 0.15 / 0.30 = 0.5
        # risk_fraction = 0.5 * 0.02 = 0.01
        self.assertAlmostEqual(result.risk_fraction, 0.01, places=5)
        self.assertEqual(result.method, "volatility")

    def test_low_volatility(self):
        """Low volatility allows larger position."""
        sizer = VolatilitySizer(target_volatility=0.15, max_risk_per_trade=0.02)
        result = sizer.calculate(
            capital=100000,
            win_rate=0.5,
            avg_win=100,
            avg_loss=100,
            current_price=50.0,
            volatility=0.075,  # Half target
        )
        # vol_ratio = 0.15 / 0.075 = 2.0 (capped)
        # risk_fraction = 2.0 * 0.02 = 0.04, but capped at 0.02
        self.assertAlmostEqual(result.risk_fraction, 0.02, places=5)

    def test_missing_volatility(self):
        """Missing volatility raises error."""
        sizer = VolatilitySizer()
        with self.assertRaises(ValueError):
            sizer.calculate(
                capital=100000,
                win_rate=0.5,
                avg_win=100,
                avg_loss=100,
                current_price=50.0,
                volatility=None,
            )


class TestPositionSizer(unittest.TestCase):
    """Tests for composite position sizer."""

    def test_kelly_method(self):
        """Composite sizer with Kelly method."""
        sizer = PositionSizer(method="kelly", fraction=0.5)
        result = sizer.calculate(
            capital=100000,
            win_rate=0.6,
            avg_win=200,
            avg_loss=100,
            current_price=50.0,
        )
        self.assertEqual(result.method, "kelly")
        self.assertGreater(result.recommended_size, 0)

    def test_volatility_method(self):
        """Composite sizer with volatility method."""
        sizer = PositionSizer(method="volatility", target_volatility=0.15)
        result = sizer.calculate(
            capital=100000,
            win_rate=0.5,
            avg_win=100,
            avg_loss=100,
            current_price=50.0,
            volatility=0.20,
        )
        self.assertEqual(result.method, "volatility")

    def test_invalid_method(self):
        """Invalid method raises error."""
        with self.assertRaises(ValueError):
            PositionSizer(method="invalid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
