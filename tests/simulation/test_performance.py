"""Tests for simulation performance analysis."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from simulation.performance import SimulationAnalyzer, StrategyComparison
from simulation.trading_loop import SimulationResult


class TestSimulationAnalyzer(unittest.TestCase):
    """Tests for simulation analyzer."""

    def test_empty_summary(self):
        """Empty analyzer returns zero stats."""
        analyzer = SimulationAnalyzer()
        summary = analyzer.summary()
        self.assertEqual(summary["total_runs"], 0)

    def test_single_result(self):
        """Single result summarized."""
        analyzer = SimulationAnalyzer()
        result = SimulationResult(
            symbol="AAPL",
            start_price=100.0,
            end_price=110.0,
            total_return_pct=10.0,
            num_trades=5,
            win_count=3,
            loss_count=2,
            total_pnl=500.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=5.0,
        )
        analyzer.add(result)
        summary = analyzer.summary()
        self.assertEqual(summary["total_runs"], 1)
        self.assertEqual(summary["avg_return_pct"], 10.0)
        self.assertEqual(summary["total_pnl"], 500.0)

    def test_multiple_results(self):
        """Multiple results aggregated."""
        analyzer = SimulationAnalyzer()
        for i in range(5):
            analyzer.add(SimulationResult(
                symbol="AAPL",
                start_price=100.0,
                end_price=100.0 + i * 5,
                total_return_pct=i * 5.0,
                num_trades=10,
                win_count=6,
                loss_count=4,
                total_pnl=i * 100.0,
                sharpe_ratio=1.0 + i * 0.1,
                max_drawdown_pct=3.0,
            ))
        summary = analyzer.summary()
        self.assertEqual(summary["total_runs"], 5)
        self.assertEqual(summary["avg_return_pct"], 10.0)  # (0+5+10+15+20)/5

    def test_consistency_score(self):
        """Consistency score calculated."""
        analyzer = SimulationAnalyzer()
        analyzer.add(SimulationResult("A", 100, 110, 10.0, 5, 3, 2, 100, 1.0, 5.0))
        analyzer.add(SimulationResult("A", 100, 90, -10.0, 5, 2, 3, -100, -1.0, 5.0))
        analyzer.add(SimulationResult("A", 100, 105, 5.0, 5, 3, 2, 50, 0.5, 5.0))
        summary = analyzer.summary()
        self.assertAlmostEqual(summary["consistency_score"], 66.66666666666667, places=10)  # 2/3 positive

    def test_compare_strategies(self):
        """Strategy comparison ranking."""
        analyzer = SimulationAnalyzer()
        momentum_results = [
            SimulationResult("A", 100, 110, 10.0, 5, 3, 2, 100, 1.0, 5.0),
            SimulationResult("A", 100, 115, 15.0, 5, 4, 1, 150, 1.5, 4.0),
        ]
        mean_rev_results = [
            SimulationResult("A", 100, 105, 5.0, 5, 3, 2, 50, 0.5, 3.0),
            SimulationResult("A", 100, 102, 2.0, 5, 2, 3, 20, 0.2, 2.0),
        ]
        for r in momentum_results:
            analyzer.add(r)
        for r in mean_rev_results:
            analyzer.add(r)

        comparisons = analyzer.compare_strategies(
            ["momentum", "mean_reversion"],
            {"momentum": momentum_results, "mean_reversion": mean_rev_results},
        )
        self.assertEqual(len(comparisons), 2)
        self.assertEqual(comparisons[0].strategy_name, "momentum")  # Higher return first
        self.assertEqual(comparisons[1].strategy_name, "mean_reversion")

    def test_rank_by_metric(self):
        """Ranking by metric."""
        analyzer = SimulationAnalyzer()
        analyzer.add(SimulationResult("A", 100, 120, 20.0, 5, 3, 2, 200, 2.0, 5.0))
        analyzer.add(SimulationResult("B", 100, 110, 10.0, 5, 3, 2, 100, 1.0, 5.0))
        analyzer.add(SimulationResult("C", 100, 130, 30.0, 5, 3, 2, 300, 3.0, 5.0))

        ranked = analyzer.rank_by_metric("total_return_pct")
        self.assertEqual(ranked[0][0], "C")
        self.assertEqual(ranked[1][0], "A")
        self.assertEqual(ranked[2][0], "B")

    def test_regime_sensitivity(self):
        """Regime sensitivity detection."""
        analyzer = SimulationAnalyzer()
        high_vol = [
            SimulationResult("A", 100, 120, 20.0, 10, 6, 4, 200, 1.5, 15.0),
            SimulationResult("A", 100, 115, 15.0, 10, 5, 5, 150, 1.2, 12.0),
        ]
        low_vol = [
            SimulationResult("A", 100, 105, 5.0, 10, 6, 4, 50, 1.0, 3.0),
            SimulationResult("A", 100, 103, 3.0, 10, 5, 5, 30, 0.8, 2.0),
        ]
        result = analyzer.detect_regime_sensitivity(high_vol, low_vol)
        self.assertEqual(result["regime_preference"], "high_vol")
        self.assertGreater(result["high_vol_avg_return"], result["low_vol_avg_return"])

    def test_clear(self):
        """Clear removes all results."""
        analyzer = SimulationAnalyzer()
        analyzer.add(SimulationResult("A", 100, 110, 10.0, 5, 3, 2, 100, 1.0, 5.0))
        self.assertEqual(analyzer.count, 1)
        analyzer.clear()
        self.assertEqual(analyzer.count, 0)

    def test_profit_factor(self):
        """Profit factor in strategy comparison."""
        analyzer = SimulationAnalyzer()
        results = [
            SimulationResult("A", 100, 110, 10.0, 5, 4, 1, 100, 1.0, 5.0),
            SimulationResult("A", 100, 90, -10.0, 5, 1, 4, -50, -0.5, 5.0),
        ]
        comparisons = analyzer.compare_strategies(
            ["test"], {"test": results}
        )
        self.assertEqual(len(comparisons), 1)
        self.assertGreater(comparisons[0].profit_factor, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
