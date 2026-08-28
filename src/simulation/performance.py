"""Simulation performance analysis and comparison.

Aggregates results from multiple simulation runs to compute
strategy rankings, statistical significance, and risk-adjusted metrics.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from simulation.trading_loop import SimulationResult


@dataclass
class StrategyComparison:
    """Comparison of multiple strategies across simulation runs."""

    strategy_name: str
    total_runs: int
    avg_return_pct: float
    avg_sharpe: float | None
    avg_max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    avg_trades_per_run: float
    total_pnl: float
    consistency_score: float  # Percentage of runs with positive return


class SimulationAnalyzer:
    """Analyzes and compares simulation results.

    Provides statistical aggregation, strategy ranking, and
    performance reporting.
    """

    def __init__(self):
        self._results: list[SimulationResult] = []

    def add(self, result: SimulationResult) -> None:
        """Add a simulation result."""
        self._results.append(result)

    def add_batch(self, results: list[SimulationResult]) -> None:
        """Add multiple results."""
        self._results.extend(results)

    def summary(self) -> dict[str, Any]:
        """Overall summary across all runs.

        Returns:
            Dictionary with aggregated statistics.
        """
        if not self._results:
            return {"total_runs": 0}

        returns = [r.total_return_pct for r in self._results]
        sharpes = [r.sharpe_ratio for r in self._results if r.sharpe_ratio is not None]
        drawdowns = [r.max_drawdown_pct for r in self._results]
        pnls = [r.total_pnl for r in self._results]
        trades = [r.num_trades for r in self._results]

        positive_runs = sum(1 for r in returns if r > 0)

        return {
            "total_runs": len(self._results),
            "avg_return_pct": statistics.mean(returns),
            "median_return_pct": statistics.median(returns),
            "std_return_pct": statistics.stdev(returns) if len(returns) > 1 else 0.0,
            "avg_sharpe": statistics.mean(sharpes) if sharpes else None,
            "avg_max_drawdown_pct": statistics.mean(drawdowns),
            "total_pnl": sum(pnls),
            "avg_trades_per_run": statistics.mean(trades),
            "consistency_score": positive_runs / len(returns) * 100,
            "win_rate": sum(r.win_count for r in self._results) / max(sum(trades), 1) * 100,
        }

    def compare_strategies(
        self,
        strategy_names: list[str],
        results_by_strategy: dict[str, list[SimulationResult]],
    ) -> list[StrategyComparison]:
        """Compare multiple strategies.

        Args:
            strategy_names: Ordered list of strategy names.
            results_by_strategy: Mapping of name to results.

        Returns:
            List of StrategyComparison, sorted by avg_return_pct desc.
        """
        comparisons: list[StrategyComparison] = []

        for name in strategy_names:
            results = results_by_strategy.get(name, [])
            if not results:
                continue

            returns = [r.total_return_pct for r in results]
            sharpes = [r.sharpe_ratio for r in results if r.sharpe_ratio is not None]
            drawdowns = [r.max_drawdown_pct for r in results]
            trades = [r.num_trades for r in results]
            pnls = [r.total_pnl for r in results]

            wins = sum(r.win_count for r in results)
            losses = sum(r.loss_count for r in results)
            profit_factor = sum(p for p in pnls if p > 0) / abs(sum(p for p in pnls if p < 0)) if any(p < 0 for p in pnls) else float("inf")

            positive = sum(1 for r in returns if r > 0)

            comparisons.append(
                StrategyComparison(
                    strategy_name=name,
                    total_runs=len(results),
                    avg_return_pct=statistics.mean(returns),
                    avg_sharpe=statistics.mean(sharpes) if sharpes else None,
                    avg_max_drawdown_pct=statistics.mean(drawdowns),
                    win_rate=wins / max(wins + losses, 1) * 100,
                    profit_factor=profit_factor,
                    avg_trades_per_run=statistics.mean(trades),
                    total_pnl=sum(pnls),
                    consistency_score=positive / len(returns) * 100,
                )
            )

        return sorted(comparisons, key=lambda c: c.avg_return_pct, reverse=True)

    def rank_by_metric(
        self,
        metric: str = "total_return_pct",
    ) -> list[tuple[str, float]]:
        """Rank runs by a specific metric.

        Args:
            metric: Attribute name to rank by.

        Returns:
            List of (symbol, metric_value) sorted descending.
        """
        ranked = []
        for r in self._results:
            val = getattr(r, metric, None)
            if val is not None:
                ranked.append((r.symbol, val))
        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def detect_regime_sensitivity(
        self,
        high_vol_results: list[SimulationResult],
        low_vol_results: list[SimulationResult],
    ) -> dict[str, Any]:
        """Compare strategy performance across volatility regimes.

        Args:
            high_vol_results: Results in high volatility.
            low_vol_results: Results in low volatility.

        Returns:
            Dictionary with regime comparison metrics.
        """
        if not high_vol_results or not low_vol_results:
            return {"error": "Insufficient data"}

        high_returns = [r.total_return_pct for r in high_vol_results]
        low_returns = [r.total_return_pct for r in low_vol_results]

        return {
            "high_vol_avg_return": statistics.mean(high_returns),
            "low_vol_avg_return": statistics.mean(low_returns),
            "high_vol_sharpe": statistics.mean([r.sharpe_ratio for r in high_vol_results if r.sharpe_ratio is not None]) if any(r.sharpe_ratio is not None for r in high_vol_results) else None,
            "low_vol_sharpe": statistics.mean([r.sharpe_ratio for r in low_vol_results if r.sharpe_ratio is not None]) if any(r.sharpe_ratio is not None for r in low_vol_results) else None,
            "high_vol_max_dd": statistics.mean([r.max_drawdown_pct for r in high_vol_results]),
            "low_vol_max_dd": statistics.mean([r.max_drawdown_pct for r in low_vol_results]),
            "regime_preference": "high_vol" if statistics.mean(high_returns) > statistics.mean(low_returns) else "low_vol",
        }

    def clear(self) -> None:
        """Clear all results."""
        self._results.clear()

    @property
    def count(self) -> int:
        """Number of results stored."""
        return len(self._results)
