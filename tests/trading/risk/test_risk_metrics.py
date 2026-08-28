"""Tests for risk metrics calculation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

import numpy as np

from trading.risk.risk_metrics import RiskMetrics, VaRModel


class TestVaRModel(unittest.TestCase):
    """Tests for Value at Risk models."""

    def test_historical_var(self):
        """Historical VaR calculation."""
        model = VaRModel(method="historical")
        returns = np.array([0.01, -0.02, 0.015, -0.01, 0.005, -0.03, 0.02, -0.015, 0.01, -0.025])
        var = model.calculate(returns, confidence=0.95, portfolio_value=100000)
        # 95% VaR should be around the 5th percentile loss
        self.assertGreater(var, 0)
        self.assertLess(var, 5000)  # Less than 5% of portfolio

    def test_parametric_var(self):
        """Parametric VaR calculation."""
        model = VaRModel(method="parametric")
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100)
        var = model.calculate(returns, confidence=0.95, portfolio_value=100000)
        self.assertGreater(var, 0)

    def test_monte_carlo_var(self):
        """Monte Carlo VaR calculation."""
        model = VaRModel(method="monte_carlo")
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.02, 100)
        var = model.calculate(returns, confidence=0.95, portfolio_value=100000)
        self.assertGreater(var, 0)

    def test_cvar(self):
        """Conditional VaR calculation."""
        model = VaRModel()
        returns = np.array([0.01, -0.02, 0.015, -0.01, 0.005, -0.03, 0.02, -0.015, 0.01, -0.025])
        cvar = model.cvar(returns, confidence=0.95, portfolio_value=100000)
        self.assertGreater(cvar, 0)
        # CVaR should be >= VaR
        var = model.calculate(returns, confidence=0.95, portfolio_value=100000)
        self.assertGreaterEqual(cvar, var)

    def test_var_confidence_levels(self):
        """99% VaR should be >= 95% VaR."""
        model = VaRModel()
        returns = np.array([0.01, -0.02, 0.015, -0.01, 0.005, -0.03, 0.02, -0.015, 0.01, -0.025])
        var_95 = model.calculate(returns, confidence=0.95, portfolio_value=100000)
        var_99 = model.calculate(returns, confidence=0.99, portfolio_value=100000)
        self.assertGreaterEqual(var_99, var_95)

    def test_empty_returns(self):
        """Empty returns raises error."""
        model = VaRModel()
        with self.assertRaises(ValueError):
            model.calculate(np.array([]), confidence=0.95)


class TestRiskMetrics(unittest.TestCase):
    """Tests for comprehensive risk metrics."""

    def setUp(self):
        """Create sample returns data."""
        np.random.seed(42)
        self.returns = np.random.normal(0.001, 0.02, 100)
        self.metrics = RiskMetrics(risk_free_rate=0.0)

    def test_risk_profile(self):
        """Comprehensive risk profile calculation."""
        profile = self.metrics.calculate_profile(self.returns, portfolio_value=100000)

        self.assertGreater(profile.var_95, 0)
        self.assertGreater(profile.var_99, 0)
        self.assertGreaterEqual(profile.var_99, profile.var_95)
        self.assertGreater(profile.cvar_95, 0)
        self.assertGreater(profile.max_drawdown, 0)
        self.assertGreaterEqual(profile.avg_drawdown, 0)
        self.assertGreaterEqual(profile.drawdown_duration, 0)
        self.assertIsInstance(profile.sharpe_ratio, float)
        self.assertIsInstance(profile.sortino_ratio, float)
        self.assertIsInstance(profile.calmar_ratio, float)
        self.assertGreater(profile.volatility, 0)
        self.assertGreaterEqual(profile.downside_deviation, 0)
        self.assertGreaterEqual(profile.win_rate, 0)
        self.assertLessEqual(profile.win_rate, 1)
        self.assertGreater(profile.profit_factor, 0)

    def test_sharpe_ratio(self):
        """Sharpe ratio with positive returns."""
        returns = np.array([0.01] * 50)  # Consistent 1% daily returns
        profile = self.metrics.calculate_profile(returns, portfolio_value=100000)
        self.assertGreater(profile.sharpe_ratio, 10)  # Very high Sharpe

    def test_drawdown(self):
        """Drawdown calculation with known pattern."""
        # Create a known drawdown: up 10%, then down 20%
        returns = np.array([0.01] * 10 + [-0.02] * 10)
        profile = self.metrics.calculate_profile(returns)
        self.assertGreater(profile.max_drawdown, 0)
        self.assertGreaterEqual(profile.avg_drawdown, 0)

    def test_profit_factor(self):
        """Profit factor with known wins/losses."""
        returns = np.array([0.01, 0.01, 0.01, -0.01, -0.01])
        profile = self.metrics.calculate_profile(returns)
        # 3 wins of 1% vs 2 losses of 1% = profit factor 1.5
        self.assertAlmostEqual(profile.profit_factor, 1.5, places=1)

    def test_rolling_var(self):
        """Rolling VaR calculation."""
        rolling = self.metrics.rolling_var(self.returns, window=20, confidence=0.95)
        self.assertEqual(len(rolling), len(self.returns))
        # First 19 should be NaN
        self.assertTrue(np.isnan(rolling[0]))
        self.assertTrue(np.isnan(rolling[18]))
        # From 20 onwards should have values
        self.assertGreater(rolling[19], 0)

    def test_empty_rolling_var(self):
        """Rolling VaR with insufficient data."""
        rolling = self.metrics.rolling_var(self.returns[:5], window=20)
        self.assertEqual(len(rolling), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
