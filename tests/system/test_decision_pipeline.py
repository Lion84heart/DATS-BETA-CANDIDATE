"""Tests for decision pipeline."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from intelligence.decisions import (
    DecisionExecutionResult,
    DecisionPhase,
    DecisionStore,
    PortfolioState,
)
from system.decision_pipeline import DecisionPipeline, PipelineContext


class TestDecisionPipeline(unittest.TestCase):
    """Tests for DecisionPipeline."""

    def setUp(self):
        """Set up fresh pipeline for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.store = DecisionStore(data_dir=self.temp_dir)
        self.pipeline = DecisionPipeline(store=self.store)

    def tearDown(self):
        """Clean up temp directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_decision(self):
        """Record a basic decision."""
        context = PipelineContext(
            symbol="AAPL",
            price=150.0,
            timestamp=1700000000.0,
            features={"rsi": 70.5, "volume": 1000000},
            strategy_name="momentum",
        )
        record = self.pipeline.record_decision(context, "Buy signal detected", confidence=0.85)

        self.assertEqual(record.market_snapshot.symbol, "AAPL")
        self.assertEqual(record.selected_strategy, "momentum")
        self.assertEqual(record.confidence_score, 0.85)
        self.assertEqual(record.reasoning_summary, "Buy signal detected")
        self.assertEqual(record.phase, DecisionPhase.SIGNAL_GENERATED)

    def test_review_status(self):
        """Decisions are marked for review."""
        context = PipelineContext(symbol="TSLA", price=200.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        status = self.pipeline.get_review_status(record.decision_id)
        self.assertEqual(status, "REVIEW_REQUIRED")

    def test_mark_reviewed(self):
        """Mark decision as reviewed."""
        context = PipelineContext(symbol="AAPL", price=150.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        self.pipeline.mark_reviewed(record.decision_id, reviewer="analyst_1", notes="Looks good")
        status = self.pipeline.get_review_status(record.decision_id)
        self.assertIn("REVIEWED_BY:analyst_1", status)
        self.assertIn("NOTES:Looks good", status)

    def test_update_execution(self):
        """Update decision with execution result."""
        context = PipelineContext(symbol="AAPL", price=150.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        execution = DecisionExecutionResult(
            order_id="ord-001",
            filled_qty=100,
            avg_price=150.5,
            slippage_bps=0.25,
            commission=1.0,
            execution_time_ms=1.0,
            status="FILLED",
        )
        updated = self.pipeline.update_execution(record.decision_id, execution)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.phase, DecisionPhase.ORDER_FILLED)
        self.assertEqual(updated.execution_result.avg_price, 150.5)

    def test_update_execution_not_found(self):
        """Update non-existent decision returns None."""
        execution = DecisionExecutionResult(
            order_id="ord-001",
            filled_qty=100,
            avg_price=150.0,
            slippage_bps=0.0,
            commission=1.0,
            execution_time_ms=1.0,
            status="FILLED",
        )
        result = self.pipeline.update_execution("nonexistent", execution)
        self.assertIsNone(result)

    def test_evaluate_outcome(self):
        """Evaluate post-trade outcome."""
        context = PipelineContext(symbol="AAPL", price=150.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        execution = DecisionExecutionResult(
            order_id="ord-001",
            filled_qty=100,
            avg_price=150.0,
            slippage_bps=0.0,
            commission=1.0,
            execution_time_ms=1.0,
            status="FILLED",
        )
        self.pipeline.update_execution(record.decision_id, execution)

        # Exit at higher price = win
        evaluated = self.pipeline.evaluate_outcome(record.decision_id, exit_price=160.0)
        self.assertIsNotNone(evaluated)
        self.assertIsNotNone(evaluated.realized_pnl)
        self.assertGreater(evaluated.realized_pnl, 0)
        self.assertEqual(evaluated.phase, DecisionPhase.POST_TRADE)

    def test_export_review_package(self):
        """Export decision as review package."""
        context = PipelineContext(symbol="AAPL", price=150.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        package = self.pipeline.export_review_package(record.decision_id)
        self.assertIsNotNone(package)
        self.assertEqual(package.decisions[0].market_snapshot.symbol, "AAPL")

    def test_export_all_pending_reviews(self):
        """Export all pending decisions."""
        for i in range(3):
            context = PipelineContext(
                symbol="AAPL", price=150.0 + i, timestamp=1700000000.0 + i
            )
            self.pipeline.record_decision(context)

        packages = self.pipeline.export_all_pending_reviews()
        self.assertEqual(len(packages), 3)

    def test_summary(self):
        """Pipeline summary."""
        for i in range(5):
            context = PipelineContext(
                symbol="AAPL", price=150.0 + i, timestamp=1700000000.0 + i
            )
            record = self.pipeline.record_decision(context)
            if i < 2:
                self.pipeline.mark_reviewed(record.decision_id)

        summary = self.pipeline.get_summary()
        self.assertEqual(summary["total_decisions_recorded"], 5)
        self.assertEqual(summary["pending_reviews"], 3)
        self.assertEqual(summary["reviewed"], 2)

    def test_advisory_only(self):
        """Exported packages are advisory and never modify production."""
        context = PipelineContext(symbol="AAPL", price=150.0, timestamp=1700000000.0)
        record = self.pipeline.record_decision(context)

        package = self.pipeline.export_review_package(record.decision_id)
        # Package should be a snapshot, not modify the original
        self.assertEqual(package.decisions[0].market_snapshot.symbol, "AAPL")
        # Verify record is still in store unchanged
        loaded = self.store.load(record.decision_id)
        self.assertEqual(loaded.market_snapshot.symbol, "AAPL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
