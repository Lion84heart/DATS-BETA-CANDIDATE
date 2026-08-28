"""Tests for post-trade evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from intelligence.decisions import DecisionRecord, DecisionExecutionResult
from intelligence.evaluation import OutcomeLabel, PostTradeEvaluator, TradeMetrics


class TestPostTradeEvaluator(unittest.TestCase):
    """Tests for post-trade evaluation."""

    def test_evaluate_completed_trade(self):
        """Evaluate a completed trade."""
        record = DecisionRecord(selected_strategy="momentum")
        record.execution_result = DecisionExecutionResult(
            order_id="o1", filled_qty=10, avg_price=100.0,
            slippage_bps=2.0, commission=0.5, execution_time_ms=5.0, status="FILLED",
        )
        record.set_outcome(exit_price=110.0, exit_timestamp=2000.0, realized_pnl=100.0, label="win")

        evaluator = PostTradeEvaluator()
        metrics = evaluator.evaluate(record)
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics.realized_pnl, 100.0)
        self.assertEqual(metrics.return_pct, 10.0)
        self.assertEqual(metrics.slippage_bps, 2.0)

    def test_evaluate_incomplete(self):
        """Incomplete trade returns None."""
        record = DecisionRecord()
        evaluator = PostTradeEvaluator()
        metrics = evaluator.evaluate(record)
        self.assertIsNone(metrics)

    def test_label_win(self):
        """Positive PnL labeled win."""
        evaluator = PostTradeEvaluator()
        self.assertEqual(evaluator.label_outcome(100.0), OutcomeLabel.WIN)

    def test_label_loss(self):
        """Negative PnL labeled loss."""
        evaluator = PostTradeEvaluator()
        self.assertEqual(evaluator.label_outcome(-50.0), OutcomeLabel.LOSS)

    def test_label_breakeven(self):
        """Near-zero PnL labeled breakeven."""
        evaluator = PostTradeEvaluator()
        self.assertEqual(evaluator.label_outcome(0.0), OutcomeLabel.BREAKEVEN)

    def test_strategy_performance(self):
        """Strategy performance aggregated."""
        evaluator = PostTradeEvaluator()
        r1 = DecisionRecord(selected_strategy="momentum")
        r1.execution_result = DecisionExecutionResult(
            "o1", 10, 100.0, 2.0, 0.5, 5.0, "FILLED",
        )
        r1.set_outcome(110.0, 2000.0, 100.0, "win")
        r2 = DecisionRecord(selected_strategy="momentum")
        r2.execution_result = DecisionExecutionResult(
            "o2", 10, 100.0, 2.0, 0.5, 5.0, "FILLED",
        )
        r2.set_outcome(90.0, 2000.0, -100.0, "loss")

        evaluator.evaluate(r1)
        evaluator.evaluate(r2)

        perf = evaluator.get_strategy_performance("momentum")
        self.assertIsNotNone(perf)
        self.assertEqual(perf.total_trades, 2)
        self.assertEqual(perf.wins, 1)
        self.assertEqual(perf.losses, 1)
        self.assertEqual(perf.win_rate, 0.5)
        self.assertEqual(perf.total_pnl, 0.0)

    def test_summary(self):
        """Overall summary generated."""
        evaluator = PostTradeEvaluator()
        r = DecisionRecord(selected_strategy="momentum")
        r.execution_result = DecisionExecutionResult(
            "o1", 10, 100.0, 2.0, 0.5, 5.0, "FILLED",
        )
        r.set_outcome(110.0, 2000.0, 100.0, "win")
        evaluator.evaluate(r)

        summary = evaluator.summary()
        self.assertEqual(summary["total_trades"], 1)
        self.assertEqual(summary["wins"], 1)
        self.assertEqual(summary["strategies"], 1)
        self.assertEqual(summary["total_pnl"], 100.0)

    def test_empty_summary(self):
        """Empty evaluator summary."""
        evaluator = PostTradeEvaluator()
        summary = evaluator.summary()
        self.assertEqual(summary["total_trades"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
