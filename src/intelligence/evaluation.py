"""Post-trade evaluation and outcome labeling.

Analyzes completed trades to generate labeled outcomes
for continuous learning and strategy improvement.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .decisions import DecisionRecord


class OutcomeLabel(Enum):
    """Classification of trade outcomes."""

    WIN = auto()
    LOSS = auto()
    BREAKEVEN = auto()
    PENDING = auto()


@dataclass
class TradeMetrics:
    """Metrics for a completed trade."""

    entry_price: float
    exit_price: float
    quantity: float
    realized_pnl: float
    return_pct: float
    slippage_bps: float
    holding_period_seconds: float
    mfe: float = 0.0  # Maximum favorable excursion
    mae: float = 0.0  # Maximum adverse excursion


@dataclass
class StrategyPerformance:
    """Aggregated performance for a strategy."""

    strategy_name: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    total_pnl: float = 0.0
    total_return_pct: float = 0.0
    avg_return_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_slippage_bps: float = 0.0
    avg_holding_seconds: float = 0.0
    returns: list[float] = field(default_factory=list)

    def update(self, metrics: TradeMetrics) -> None:
        """Update statistics with a new trade."""
        self.total_trades += 1
        self.total_pnl += metrics.realized_pnl
        self.total_return_pct += metrics.return_pct
        self.returns.append(metrics.return_pct)

        if metrics.realized_pnl > 0:
            self.wins += 1
        elif metrics.realized_pnl < 0:
            self.losses += 1
        else:
            self.breakeven += 1

        self.avg_return_pct = statistics.mean(self.returns) if self.returns else 0.0
        self.win_rate = self.wins / self.total_trades if self.total_trades > 0 else 0.0

        gross_profit = sum(r for r in self.returns if r > 0)
        gross_loss = abs(sum(r for r in self.returns if r < 0))
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        self.avg_slippage_bps = sum(
            t.slippage_bps for t in getattr(self, "_trades", [])
        ) / self.total_trades if hasattr(self, "_trades") else 0.0


class PostTradeEvaluator:
    """Evaluates completed trades and generates learning labels.

    Labels trades as win/loss/breakeven and computes strategy-level
    performance metrics for continuous improvement.
    """

    BREAKEVEN_THRESHOLD: float = 0.0001  # 1 bps

    def __init__(self):
        self._trade_metrics: list[TradeMetrics] = []
        self._strategy_stats: dict[str, StrategyPerformance] = {}

    def evaluate(self, record: DecisionRecord) -> TradeMetrics | None:
        """Evaluate a completed trade decision.

        Args:
            record: DecisionRecord with execution and outcome data.

        Returns:
            TradeMetrics or None if trade not completed.
        """
        if not record.execution_result or record.realized_pnl is None:
            return None

        entry = record.execution_result.avg_price if record.execution_result else 0.0
        exit_price = record.exit_price or entry
        qty = record.execution_result.filled_qty if record.execution_result else 0.0

        pnl = record.realized_pnl
        ret_pct = ((exit_price - entry) / entry) * 100 if entry != 0 else 0.0

        slippage = record.execution_result.slippage_bps if record.execution_result else 0.0
        hold_time = record.holding_period_seconds or 0.0

        metrics = TradeMetrics(
            entry_price=entry,
            exit_price=exit_price,
            quantity=qty,
            realized_pnl=pnl,
            return_pct=ret_pct,
            slippage_bps=slippage,
            holding_period_seconds=hold_time,
        )

        self._trade_metrics.append(metrics)

        # Update strategy stats
        strategy = record.selected_strategy
        if strategy not in self._strategy_stats:
            self._strategy_stats[strategy] = StrategyPerformance(strategy_name=strategy)
        self._strategy_stats[strategy].update(metrics)

        return metrics

    def label_outcome(self, realized_pnl: float) -> OutcomeLabel:
        """Label a trade outcome.

        Args:
            realized_pnl: Trade P&L.

        Returns:
            OutcomeLabel classification.
        """
        if realized_pnl == 0:
            return OutcomeLabel.BREAKEVEN
        threshold = abs(realized_pnl) * self.BREAKEVEN_THRESHOLD
        if abs(realized_pnl) < threshold:
            return OutcomeLabel.BREAKEVEN
        if realized_pnl > 0:
            return OutcomeLabel.WIN
        return OutcomeLabel.LOSS

    def get_strategy_performance(self, strategy_name: str) -> StrategyPerformance | None:
        """Get performance stats for a strategy.

        Args:
            strategy_name: Strategy identifier.

        Returns:
            StrategyPerformance or None.
        """
        return self._strategy_stats.get(strategy_name)

    def get_all_strategy_performance(self) -> dict[str, StrategyPerformance]:
        """Get performance for all strategies."""
        return self._strategy_stats.copy()

    def summary(self) -> dict[str, Any]:
        """Overall evaluation summary."""
        total = len(self._trade_metrics)
        if total == 0:
            return {"total_trades": 0}

        pnls = [t.realized_pnl for t in self._trade_metrics]
        returns = [t.return_pct for t in self._trade_metrics]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": total - wins - losses,
            "win_rate": wins / total,
            "total_pnl": sum(pnls),
            "avg_pnl": statistics.mean(pnls),
            "avg_return_pct": statistics.mean(returns),
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            "strategies": len(self._strategy_stats),
        }
