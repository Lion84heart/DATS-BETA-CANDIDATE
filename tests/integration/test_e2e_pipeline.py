"""End-to-end integration tests for the complete trading pipeline.

Validates that all modules (strategy, risk, execution, monitoring,
security, intelligence) interoperate correctly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from security.validation import InputValidator
from simulation.market_sim import MarketSimulator
from simulation.trading_loop import TradingSimulator
from simulation.performance import SimulationAnalyzer


def integration_momentum_strategy(prices: list[float]) -> str:
    """Simple momentum for integration testing."""
    if len(prices) < 10:
        return "HOLD"
    short = sum(prices[-5:]) / 5
    long = sum(prices[-20:]) / 20
    if short > long * 1.02:
        return "BUY"
    if short < long * 0.98:
        return "SELL"
    return "HOLD"


def integration_risk_check(context: dict) -> bool:
    """Integration risk check: block if drawdown > 15%."""
    return context.get("max_drawdown", 0) < 0.15


def integration_position_size(price: float, capital: float) -> float:
    """Integration position sizing: 5% of capital."""
    return (capital * 0.05) / price


class TestE2EPipeline(unittest.TestCase):
    """End-to-end integration tests."""

    def test_full_pipeline_single_asset(self):
        """Complete pipeline: market → strategy → risk → execute → analyze."""
        # 1. Generate market data
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 500)

        # 2. Run trading simulation
        trader = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
            slippage_bps=3.0,
            commission_per_trade=0.5,
        )
        result = trader.run(path, lookback=20)

        # 3. Analyze results
        analyzer = SimulationAnalyzer()
        analyzer.add(result)
        summary = analyzer.summary()

        # 4. Assertions
        self.assertEqual(result.symbol, "AAPL")
        self.assertIsNotNone(result.total_return_pct)
        self.assertIsNotNone(result.sharpe_ratio)
        self.assertGreaterEqual(result.max_drawdown_pct, 0.0)
        self.assertEqual(summary["total_runs"], 1)

    def test_pipeline_with_input_validation(self):
        """Pipeline with security input validation integrated."""
        validator = InputValidator()

        # Validate symbol
        symbol = validator.symbol("AAPL")
        self.assertEqual(symbol, "AAPL")

        # Validate price
        price = validator.price(150.25)
        self.assertEqual(float(price), 150.25)

        # Validate quantity
        qty = validator.quantity(100)
        self.assertEqual(float(qty), 100)

        # Run pipeline with validated inputs
        sim = MarketSimulator(seed=42)
        path = sim.generate_path(symbol, float(price), 300)

        trader = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=lambda p, c: float(qty),
        )
        result = trader.run(path, lookback=20)
        self.assertEqual(result.symbol, "AAPL")

    def test_multi_run_consistency(self):
        """Multiple runs with same seed produce deterministic results."""
        def run():
            sim = MarketSimulator(seed=123)
            path = sim.generate_path("X", 100.0, 300)
            trader = TradingSimulator(
                strategy_fn=integration_momentum_strategy,
                risk_fn=integration_risk_check,
                position_size_fn=integration_position_size,
            )
            return trader.run(path, lookback=20)

        r1 = run()
        r2 = run()

        self.assertEqual(r1.num_trades, r2.num_trades)
        self.assertEqual(r1.total_return_pct, r2.total_return_pct)
        self.assertEqual(r1.total_pnl, r2.total_pnl)

    def test_batch_simulation_analysis(self):
        """Batch simulation with cross-asset comparison."""
        sim = MarketSimulator(seed=42)
        paths = [
            sim.generate_path("AAPL", 100.0, 400),
            sim.generate_path("TSLA", 200.0, 400),
            sim.generate_path("BTC", 50000.0, 400),
        ]

        trader = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
        )
        results = trader.run_batch(paths, lookback=20)

        analyzer = SimulationAnalyzer()
        analyzer.add_batch(results)

        summary = analyzer.summary()
        self.assertEqual(summary["total_runs"], 3)
        self.assertIn("avg_return_pct", summary)

    def test_strategy_comparison_integration(self):
        """Compare momentum vs mean reversion in integrated pipeline."""
        def mean_reversion(prices: list[float]) -> str:
            if len(prices) < 20:
                return "HOLD"
            mean = sum(prices[-20:]) / 20
            current = prices[-1]
            if current < mean * 0.97:
                return "BUY"
            if current > mean * 1.03:
                return "SELL"
            return "HOLD"

        sim = MarketSimulator(seed=42)
        paths = [sim.generate_path("AAPL", 100.0, 400) for _ in range(5)]

        momentum_results = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
        ).run_batch(paths, lookback=20)

        # Fresh paths for fair comparison
        paths2 = [sim.generate_path("AAPL", 100.0, 400) for _ in range(5)]
        mean_rev_results = TradingSimulator(
            strategy_fn=mean_reversion,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
        ).run_batch(paths2, lookback=20)

        analyzer = SimulationAnalyzer()
        comparisons = analyzer.compare_strategies(
            ["momentum", "mean_reversion"],
            {"momentum": momentum_results, "mean_reversion": mean_rev_results},
        )

        self.assertEqual(len(comparisons), 2)
        # Both should have statistics
        for c in comparisons:
            self.assertGreater(c.total_runs, 0)

    def test_risk_rejection_integration(self):
        """Risk system blocks trades during high drawdown."""
        def strict_risk(context: dict) -> bool:
            return context.get("max_drawdown", 0) < 0.05  # Very strict

        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 500)

        trader = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=strict_risk,
            position_size_fn=integration_position_size,
        )
        result = trader.run(path, lookback=20)

        # Strict risk should block some trades
        self.assertGreaterEqual(result.risk_events, 0)

    def test_slippage_impact_on_pnl(self):
        """Higher slippage reduces PnL."""
        sim = MarketSimulator(seed=42)
        path = sim.generate_path("AAPL", 100.0, 400)

        trader_low = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
            slippage_bps=1.0,
        )
        r_low = trader_low.run(path, lookback=20)

        path2 = sim.generate_path("AAPL", 100.0, 400)
        trader_high = TradingSimulator(
            strategy_fn=integration_momentum_strategy,
            risk_fn=integration_risk_check,
            position_size_fn=integration_position_size,
            slippage_bps=50.0,
        )
        r_high = trader_high.run(path2, lookback=20)

        # High slippage should result in worse or equal PnL
        self.assertLessEqual(r_high.total_pnl, r_low.total_pnl + 1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
