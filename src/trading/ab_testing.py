"""DATS — A/B Testing Framework.

Statistical comparison of two strategies using t-tests and
multi-metric winner determination.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from scipy import stats

from trading.backtest import BacktestEngine
from trading.base_strategy import BaseStrategy
from trading.schemas import (
    ABTest,
    ABTestResult,
    PerformanceMetrics,
)

logger = logging.getLogger(__name__)


class ABTestFramework:
    """A/B testing framework for comparing strategies.

    Performs statistical significance testing (t-test on trade returns)
    and determines a winner based on multiple performance metrics.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
    ) -> None:
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate

    async def create_test(
        self,
        name: str,
        strategy_a: BaseStrategy,
        strategy_b: BaseStrategy,
        ohlcv_df: pd.DataFrame,
        confidence_level: float = 0.95,
    ) -> ABTest:
        """Create an A/B test configuration.

        Args:
            name: Test name / identifier.
            strategy_a: First strategy (variant A).
            strategy_b: Second strategy (variant B).
            ohlcv_df: OHLCV DataFrame for testing.
            confidence_level: Statistical confidence level.

        Returns:
            ABTest configuration object.
        """
        return ABTest(
            name=name,
            strategy_a_name=strategy_a.name,
            strategy_b_name=strategy_b.name,
            confidence_level=confidence_level,
            status="pending",
        )

    async def run_test(
        self,
        test: ABTest,
        ohlcv_df: pd.DataFrame,
        strategy_a: BaseStrategy | None = None,
        strategy_b: BaseStrategy | None = None,
    ) -> ABTestResult:
        """Run an A/B test between two strategies.

        Executes both strategies on the same data and compares results
        using statistical tests.

        Args:
            test: ABTest configuration.
            ohlcv_df: OHLCV DataFrame.
            strategy_a: Strategy A instance (optional if names known).
            strategy_b: Strategy B instance (optional if names known).

        Returns:
            ABTestResult with winner determination and recommendation.
        """
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
        )

        # Run both strategies
        if strategy_a is not None:
            result_a = engine.run(strategy_a, ohlcv_df)
        else:
            raise ValueError("strategy_a is required for run_test")

        if strategy_b is not None:
            result_b = engine.run(strategy_b, ohlcv_df)
        else:
            raise ValueError("strategy_b is required for run_test")

        # Statistical test on trade returns
        returns_a = [t.pnl for t in result_a.trades] if result_a.trades else [0.0]
        returns_b = [t.pnl for t in result_b.trades] if result_b.trades else [0.0]

        if len(returns_a) > 1 and len(returns_b) > 1:
            # Welch's t-test (unequal variances)
            t_stat, p_value = stats.ttest_ind(returns_a, returns_b, equal_var=False)
        else:
            p_value = 1.0  # Not enough data

        alpha = 1.0 - test.confidence_level
        is_significant = p_value < alpha

        # Winner determination using composite score
        score_a = self._compute_composite_score(result_a.metrics)
        score_b = self._compute_composite_score(result_b.metrics)

        if is_significant:
            if score_a > score_b:
                winner = "A"
            elif score_b > score_a:
                winner = "B"
            else:
                winner = "tie"
        else:
            # Not statistically significant — call it a tie
            winner = "tie"

        # Recommendation
        if winner == "A":
            recommendation = (
                f"Strategy A ({test.strategy_a_name}) outperforms B "
                f"with {test.confidence_level*100:.0f}% confidence (p={p_value:.4f}). "
                f"Sharpe A={result_a.metrics.sharpe_ratio:.3f} vs "
                f"B={result_b.metrics.sharpe_ratio:.3f}. "
                f"Recommend deploying Strategy A."
            )
        elif winner == "B":
            recommendation = (
                f"Strategy B ({test.strategy_b_name}) outperforms A "
                f"with {test.confidence_level*100:.0f}% confidence (p={p_value:.4f}). "
                f"Sharpe B={result_b.metrics.sharpe_ratio:.3f} vs "
                f"A={result_a.metrics.sharpe_ratio:.3f}. "
                f"Recommend deploying Strategy B."
            )
        else:
            if score_a > score_b:
                leader = test.strategy_a_name
                diff = score_a - score_b
            else:
                leader = test.strategy_b_name
                diff = score_b - score_a
            recommendation = (
                f"No statistically significant difference (p={p_value:.4f}). "
                f"{leader} shows slightly better performance (score diff={diff:.4f}), "
                f"but the result is not significant at {test.confidence_level*100:.0f}% confidence. "
                f"Consider running a longer test or collecting more trade data."
            )

        test.status = "completed"

        return ABTestResult(
            test_name=test.name,
            strategy_a_name=test.strategy_a_name,
            strategy_b_name=test.strategy_b_name,
            strategy_a_metrics=result_a.metrics,
            strategy_b_metrics=result_b.metrics,
            winner=winner,
            p_value=p_value,
            confidence=test.confidence_level,
            recommendation=recommendation,
        )

    def _compute_composite_score(self, metrics: PerformanceMetrics) -> float:
        """Compute a composite performance score.

        Combines multiple metrics into a single score for comparison.
        Higher is better.
        """
        # Normalize and weight key metrics
        sharpe_score = max(0, metrics.sharpe_ratio) * 0.3
        return_score = max(0, metrics.total_return) * 0.25
        win_rate_score = metrics.win_rate * 0.15
        calmar_score = max(0, metrics.calmar_ratio) * 0.15
        expectancy_score = max(0, metrics.expectancy) * 100 * 0.15

        return sharpe_score + return_score + win_rate_score + calmar_score + expectancy_score

    async def compare_multiple(
        self,
        strategies: list[BaseStrategy],
        ohlcv_df: pd.DataFrame,
        confidence_level: float = 0.95,
    ) -> pd.DataFrame:
        """Compare multiple strategies pairwise.

        Args:
            strategies: List of strategies to compare.
            ohlcv_df: OHLCV DataFrame.
            confidence_level: Statistical confidence level.

        Returns:
            DataFrame with pairwise comparison results.
        """
        engine = BacktestEngine(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate,
        )

        # Run all strategies
        results: dict[str, Any] = {}
        for s in strategies:
            results[s.name] = engine.run(s, ohlcv_df)

        # Pairwise comparisons
        rows: list[dict[str, Any]] = []
        names = [s.name for s in strategies]
        for i, name_a in enumerate(names):
            for name_b in names[i + 1 :]:
                returns_a = [t.pnl for t in results[name_a].trades] or [0.0]
                returns_b = [t.pnl for t in results[name_b].trades] or [0.0]

                if len(returns_a) > 1 and len(returns_b) > 1:
                    _, p_value = stats.ttest_ind(returns_a, returns_b, equal_var=False)
                else:
                    p_value = 1.0

                score_a = self._compute_composite_score(results[name_a].metrics)
                score_b = self._compute_composite_score(results[name_b].metrics)

                if p_value < (1.0 - confidence_level):
                    winner = name_a if score_a > score_b else name_b
                else:
                    winner = "tie"

                rows.append({
                    "strategy_a": name_a,
                    "strategy_b": name_b,
                    "sharpe_a": round(results[name_a].metrics.sharpe_ratio, 4),
                    "sharpe_b": round(results[name_b].metrics.sharpe_ratio, 4),
                    "return_a": round(results[name_a].metrics.total_return, 4),
                    "return_b": round(results[name_b].metrics.total_return, 4),
                    "p_value": round(p_value, 6),
                    "winner": winner,
                })

        return pd.DataFrame(rows)
