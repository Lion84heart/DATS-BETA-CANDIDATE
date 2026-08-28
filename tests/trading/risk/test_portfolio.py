"""Tests for portfolio tracking and exposure management."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

import numpy as np

from trading.risk.portfolio import (
    ExposureLimit,
    PortfolioTracker,
    Position,
)


class TestPosition(unittest.TestCase):
    """Tests for Position dataclass."""

    def test_long_position(self):
        """Long position calculations."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=160.0, side="long")
        pos.update_price(160.0)  # Calculate unrealized PnL
        self.assertEqual(pos.market_value, 16000.0)
        self.assertEqual(pos.notional, 16000.0)
        self.assertEqual(pos.unrealized_pnl, 1000.0)

    def test_short_position(self):
        """Short position calculations."""
        pos = Position(symbol="TSLA", quantity=50, entry_price=200.0, current_price=190.0, side="short")
        pos.update_price(190.0)  # Calculate unrealized PnL
        self.assertEqual(pos.market_value, -9500.0)
        self.assertEqual(pos.notional, 9500.0)
        self.assertEqual(pos.unrealized_pnl, 500.0)  # 50 * (200 - 190)

    def test_update_price(self):
        """Price update recalculates P&L."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        self.assertEqual(pos.unrealized_pnl, 0.0)

        pos.update_price(155.0)
        self.assertEqual(pos.unrealized_pnl, 500.0)
        self.assertEqual(pos.current_price, 155.0)


class TestPortfolioTracker(unittest.TestCase):
    """Tests for portfolio tracker."""

    def setUp(self):
        """Create portfolio tracker."""
        self.limits = ExposureLimit(
            max_position_pct=0.25,
            max_portfolio_leverage=2.0,
            max_short_exposure_pct=0.20,
            min_cash_buffer_pct=0.05,
        )
        self.portfolio = PortfolioTracker(initial_capital=100000, exposure_limits=self.limits)

    def test_initial_state(self):
        """Portfolio starts with all cash."""
        self.assertEqual(self.portfolio.cash, 100000)
        self.assertEqual(self.portfolio.total_value, 100000)
        self.assertEqual(len(self.portfolio._positions), 0)

    def test_add_long_position(self):
        """Add a long position."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        self.portfolio.add_position(pos)

        self.assertEqual(self.portfolio.cash, 85000.0)  # 100k - 100*150
        self.assertEqual(self.portfolio.total_value, 100000.0)  # 85k cash + 15k position
        self.assertEqual(len(self.portfolio._positions), 1)

    def test_position_limit(self):
        """Position exceeding limit raises error."""
        # Try to add 50% of portfolio in one position (limit is 25%)
        pos = Position(symbol="AAPL", quantity=400, entry_price=150.0, current_price=150.0, side="long")
        with self.assertRaises(ValueError) as ctx:
            self.portfolio.add_position(pos)
        self.assertIn("exceeds limit", str(ctx.exception))

    def test_cash_buffer(self):
        """Position that breaches cash buffer raises error."""
        # Use a 90% position limit but 10% cash buffer to test cash buffer
        portfolio = PortfolioTracker(
            initial_capital=100000,
            exposure_limits=ExposureLimit(
                max_position_pct=0.95,
                min_cash_buffer_pct=0.10,
            ),
        )
        # 90% of capital = 90k, leaving 10k cash = 10% buffer
        # Try to use 91% which would leave 9k = 9% buffer (below 10%)
        pos = Position(symbol="AAPL", quantity=607, entry_price=150.0, current_price=150.0, side="long")
        with self.assertRaises(ValueError) as ctx:
            portfolio.add_position(pos)
        self.assertIn("cash", str(ctx.exception).lower())

    def test_remove_position(self):
        """Remove a position and realize P&L."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=160.0, side="long")
        pos.update_price(160.0)  # Ensure unrealized PnL is calculated
        self.portfolio.add_position(pos)

        removed = self.portfolio.remove_position("AAPL")
        self.assertEqual(removed.symbol, "AAPL")
        self.assertEqual(self.portfolio._realized_pnl, 1000.0)
        # Cash restored at current price
        self.assertEqual(self.portfolio.cash, 101000.0)

    def test_update_prices(self):
        """Update prices affects portfolio value."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        self.portfolio.add_position(pos)

        self.portfolio.update_prices({"AAPL": 160.0})
        self.assertEqual(self.portfolio.total_value, 101000.0)

    def test_exposure_report(self):
        """Exposure report generation."""
        pos1 = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        pos2 = Position(symbol="TSLA", quantity=50, entry_price=200.0, current_price=200.0, side="long")
        self.portfolio.add_position(pos1)
        self.portfolio.add_position(pos2)

        report = self.portfolio.exposure_report()
        self.assertEqual(report["total_value"], 100000.0)
        self.assertEqual(report["gross_exposure"], 25000.0)
        self.assertEqual(report["gross_leverage"], 0.25)
        self.assertEqual(report["position_count"], 2)

    def test_snapshot(self):
        """Portfolio snapshot."""
        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=155.0, side="long")
        pos.update_price(155.0)
        self.portfolio.add_position(pos)

        snap = self.portfolio.snapshot(timestamp=1234567890.0)
        self.assertEqual(snap.timestamp, 1234567890.0)
        self.assertEqual(snap.total_value, 100500.0)
        self.assertEqual(snap.unrealized_pnl, 500.0)
        self.assertEqual(len(snap.positions), 1)

    def test_correlation_matrix(self):
        """Correlation matrix calculation."""
        pos1 = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        pos2 = Position(symbol="TSLA", quantity=50, entry_price=200.0, current_price=200.0, side="long")
        self.portfolio.add_position(pos1)
        self.portfolio.add_position(pos2)

        np.random.seed(42)
        returns = {
            "AAPL": np.random.normal(0.001, 0.02, 50),
            "TSLA": np.random.normal(0.001, 0.02, 50),
        }
        corr = self.portfolio.correlation_matrix(returns)
        self.assertIn("AAPL", corr)
        self.assertIn("TSLA", corr)
        # Correlation should be between -1 and 1
        if "TSLA" in corr["AAPL"]:
            self.assertGreaterEqual(corr["AAPL"]["TSLA"], -1.0)
            self.assertLessEqual(corr["AAPL"]["TSLA"], 1.0)

    def test_event_callback(self):
        """Event callback fired."""
        events = []
        self.portfolio.on_event(lambda e, d: events.append((e, d)))

        pos = Position(symbol="AAPL", quantity=100, entry_price=150.0, current_price=150.0, side="long")
        self.portfolio.add_position(pos)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "position_added")

    def test_short_position_limit(self):
        """Short exposure limit enforced."""
        # Add a small long position first
        long_pos = Position(symbol="AAPL", quantity=10, entry_price=150.0, current_price=150.0, side="long")
        self.portfolio.add_position(long_pos)

        # Try to add short position that is under position limit (25%) but over short limit (20%)
        # $22k short = 22% of $100k, which is under 25% position limit but over 20% short limit
        short_pos = Position(symbol="TSLA", quantity=110, entry_price=200.0, current_price=200.0, side="short")
        with self.assertRaises(ValueError) as ctx:
            self.portfolio.add_position(short_pos)
        self.assertIn("Short exposure", str(ctx.exception))

    def test_history(self):
        """Snapshot history maintained."""
        self.assertEqual(len(self.portfolio.history), 0)
        self.portfolio.snapshot()
        self.assertEqual(len(self.portfolio.history), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
