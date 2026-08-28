"""Tests for decision intelligence framework."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from intelligence.decisions import (
    DecisionExecutionResult,
    DecisionPackage,
    DecisionPhase,
    DecisionRecord,
    DecisionStore,
    FeatureVector,
    MarketSnapshot,
    PortfolioState,
    RiskAssessment,
)


class TestDecisionRecord(unittest.TestCase):
    """Tests for decision recording."""

    def test_create_record(self):
        """Record created with UUID."""
        record = DecisionRecord()
        self.assertIsNotNone(record.decision_id)
        self.assertEqual(len(record.decision_id), 36)
        self.assertEqual(record.phase, DecisionPhase.SIGNAL_GENERATED)

    def test_market_snapshot(self):
        """Market snapshot attached."""
        record = DecisionRecord(
            market_snapshot=MarketSnapshot(
                symbol="AAPL",
                timestamp=1000.0,
                price=150.0,
                bid=149.9,
                ask=150.1,
            )
        )
        self.assertEqual(record.market_snapshot.symbol, "AAPL")

    def test_feature_vector(self):
        """Feature vector recorded."""
        fv = FeatureVector(
            features={"rsi": 65.0, "macd": 0.5},
            feature_names=["rsi", "macd"],
        )
        record = DecisionRecord(feature_vector=fv)
        self.assertEqual(record.feature_vector.to_array(), [65.0, 0.5])

    def test_risk_assessment(self):
        """Risk assessment recorded."""
        risk = RiskAssessment(
            var_95=0.05,
            passed_checks=["position_size", "leverage"],
            failed_checks=[],
        )
        record = DecisionRecord(risk_assessment=risk)
        self.assertTrue(record.risk_assessment.passed_checks)

    def test_portfolio_state(self):
        """Portfolio state recorded."""
        ps = PortfolioState(
            total_value=100000.0,
            cash=50000.0,
            unrealized_pnl=1000.0,
            open_positions={"AAPL": {"qty": 100, "avg_price": 145.0}},
        )
        record = DecisionRecord(portfolio_state=ps)
        self.assertEqual(record.portfolio_state.total_value, 100000.0)

    def test_execution_result(self):
        """Execution result recorded."""
        er = DecisionExecutionResult(
            order_id="ord-1",
            filled_qty=100.0,
            avg_price=150.05,
            slippage_bps=5.0,
            commission=1.0,
            execution_time_ms=12.5,
            status="FILLED",
        )
        record = DecisionRecord(execution_result=er)
        self.assertEqual(record.execution_result.status, "FILLED")

    def test_set_outcome(self):
        """Outcome set post-trade."""
        record = DecisionRecord(timestamp=1000.0)
        record.execution_result = DecisionExecutionResult(
            order_id="ord-1", filled_qty=100, avg_price=150.0,
            slippage_bps=2.0, commission=1.0, execution_time_ms=10.0, status="FILLED",
        )
        record.set_outcome(exit_price=155.0, exit_timestamp=2000.0, realized_pnl=500.0, label="win")
        self.assertEqual(record.outcome_label, "win")
        self.assertEqual(record.realized_pnl, 500.0)
        self.assertEqual(record.holding_period_seconds, 1000.0)
        self.assertEqual(record.phase, DecisionPhase.POST_TRADE)

    def test_to_json(self):
        """Record serializes to JSON."""
        record = DecisionRecord(reasoning_summary="Buy signal triggered")
        json_str = record.to_json()
        self.assertIn("decision_id", json_str)
        self.assertIn("Buy signal triggered", json_str)


class TestDecisionPackage(unittest.TestCase):
    """Tests for decision packages."""

    def test_add_decisions(self):
        """Decisions added to package."""
        pkg = DecisionPackage(description="Daily review")
        pkg.add(DecisionRecord())
        pkg.add(DecisionRecord())
        self.assertEqual(len(pkg.decisions), 2)

    def test_generate_report(self):
        """Report generated with statistics."""
        pkg = DecisionPackage(description="Test")
        d1 = DecisionRecord(selected_strategy="momentum", confidence_score=0.8)
        d1.set_outcome(110.0, 2000.0, 100.0, "win")
        d1.execution_result = DecisionExecutionResult(
            "o1", 10, 100.0, 2.0, 0.5, 5.0, "FILLED",
        )
        d2 = DecisionRecord(selected_strategy="momentum", confidence_score=0.7)
        d2.set_outcome(90.0, 2000.0, -50.0, "loss")
        d2.execution_result = DecisionExecutionResult(
            "o2", 10, 100.0, 3.0, 0.5, 5.0, "FILLED",
        )
        pkg.add(d1)
        pkg.add(d2)

        report = pkg.generate_report()
        self.assertEqual(report["total_decisions"], 2)
        self.assertEqual(report["outcomes"]["wins"], 1)
        self.assertEqual(report["outcomes"]["losses"], 1)
        self.assertEqual(report["win_rate"], 0.5)
        self.assertAlmostEqual(report["avg_confidence"], 0.75)
        self.assertIn("momentum", report["strategies_used"])

    def test_export(self):
        """Package exported to file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            pkg = DecisionPackage(description="Test export")
            pkg.add(DecisionRecord())
            pkg.export(path)
            self.assertTrue(Path(path).exists())
            self.assertGreater(Path(path).stat().st_size, 0)
        finally:
            Path(path).unlink()


class TestDecisionStore(unittest.TestCase):
    """Tests for decision store."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_save_and_load(self):
        """Decision saved and loaded."""
        store = DecisionStore(self.temp_dir)
        record = DecisionRecord(
            selected_strategy="mean_reversion",
            market_snapshot=MarketSnapshot(
                symbol="BTC", timestamp=1000.0, price=50000.0, bid=49990.0, ask=50010.0,
            ),
        )
        path = store.save(record)
        self.assertTrue(path.exists())

        loaded = store.load(record.decision_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.selected_strategy, "mean_reversion")

    def test_query_by_symbol(self):
        """Query by symbol filter."""
        store = DecisionStore(self.temp_dir)
        store.save(DecisionRecord(
            market_snapshot=MarketSnapshot(symbol="AAPL", timestamp=1.0, price=150.0, bid=149.0, ask=151.0),
        ))
        store.save(DecisionRecord(
            market_snapshot=MarketSnapshot(symbol="TSLA", timestamp=2.0, price=200.0, bid=199.0, ask=201.0),
        ))
        results = store.query(symbol="AAPL")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].market_snapshot.symbol, "AAPL")

    def test_query_by_strategy(self):
        """Query by strategy filter."""
        store = DecisionStore(self.temp_dir)
        store.save(DecisionRecord(selected_strategy="momentum"))
        store.save(DecisionRecord(selected_strategy="mean_reversion"))
        results = store.query(strategy="momentum")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].selected_strategy, "momentum")

    def test_count(self):
        """Count decisions in store."""
        store = DecisionStore(self.temp_dir)
        self.assertEqual(store.count(), 0)
        store.save(DecisionRecord())
        self.assertEqual(store.count(), 1)

    def test_query_limit(self):
        """Query respects limit."""
        store = DecisionStore(self.temp_dir)
        for _ in range(10):
            store.save(DecisionRecord())
        results = store.query(limit=3)
        self.assertEqual(len(results), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
