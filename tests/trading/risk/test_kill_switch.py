"""Tests for kill switch / circuit breaker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from trading.risk.kill_switch import (
    KillSwitch,
    KillSwitchConfig,
    KillSwitchState,
    KillSwitchTrigger,
)


class TestKillSwitch(unittest.TestCase):
    """Tests for kill switch circuit breaker."""

    def setUp(self):
        """Create kill switch with tight limits for testing."""
        self.config = KillSwitchConfig(
            max_drawdown_pct=0.10,
            daily_loss_limit_pct=0.20,  # High daily limit so drawdown triggers first
            consecutive_losses=3,
            cooldown_seconds=1,
            auto_rearm=True,
        )
        self.ks = KillSwitch(self.config)

    def test_initial_state(self):
        """Kill switch starts disarmed."""
        self.assertEqual(self.ks.state, KillSwitchState.DISARMED)
        self.assertFalse(self.ks.is_armed)
        self.assertFalse(self.ks.is_triggered)

    def test_arm_disarm(self):
        """Arm and disarm the kill switch."""
        asyncio.run(self.ks.arm())
        self.assertEqual(self.ks.state, KillSwitchState.ARMED)
        self.assertTrue(self.ks.is_armed)

        asyncio.run(self.ks.disarm())
        self.assertEqual(self.ks.state, KillSwitchState.DISARMED)
        self.assertFalse(self.ks.is_armed)

    def test_max_drawdown_trigger(self):
        """Kill switch triggers on max drawdown."""
        asyncio.run(self.ks.arm())

        # Simulate trades leading to drawdown
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=0))
        asyncio.run(self.ks.check_trade(portfolio_value=95000, trade_pnl=-5000))
        asyncio.run(self.ks.check_trade(portfolio_value=89000, trade_pnl=-6000))

        # Drawdown = (100000 - 89000) / 100000 = 11% > 10%
        allowed = asyncio.run(self.ks.check_trade(portfolio_value=89000, trade_pnl=0))
        self.assertFalse(allowed)
        self.assertTrue(self.ks.is_triggered)
        self.assertEqual(self.ks.event_history[-1].trigger, KillSwitchTrigger.MAX_DRAWDOWN)

    def test_daily_loss_limit(self):
        """Kill switch triggers on daily loss limit."""
        asyncio.run(self.ks.arm())

        # Mix wins and losses to avoid consecutive loss trigger
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=1000))   # Win
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-5000))  # Loss
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=500))    # Win
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-3000))  # Loss
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=200))   # Win
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-2000))  # Loss
        # Total daily loss = 10000 = 10% of 100000, exceeds 5% limit
        # But wait, we changed config to 20%... let me use a larger loss
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-12000)) # Total = 22000 = 22%

        allowed = asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=0))
        self.assertFalse(allowed)
        self.assertEqual(self.ks.event_history[-1].trigger, KillSwitchTrigger.DAILY_LOSS_LIMIT)

    def test_consecutive_losses(self):
        """Kill switch triggers on consecutive losses."""
        asyncio.run(self.ks.arm())

        # 3 consecutive losses
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-100))
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-200))
        allowed = asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-300))

        self.assertFalse(allowed)
        self.assertEqual(self.ks.event_history[-1].trigger, KillSwitchTrigger.CONSECUTIVE_LOSSES)

    def test_win_resets_consecutive(self):
        """Winning trade resets consecutive loss counter."""
        asyncio.run(self.ks.arm())

        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-100))
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-200))
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=500))  # Win
        asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=-100))

        # Should still be armed (only 1 consecutive loss after win)
        self.assertTrue(self.ks.is_armed)

    def test_manual_halt(self):
        """Manual halt triggers kill switch."""
        asyncio.run(self.ks.arm())
        event = asyncio.run(self.ks.manual_halt("Emergency stop"))

        self.assertTrue(self.ks.is_triggered)
        self.assertEqual(event.trigger, KillSwitchTrigger.MANUAL)
        self.assertEqual(event.reason, "Emergency stop")

    def test_manual_reset(self):
        """Manual reset after trigger."""
        asyncio.run(self.ks.arm())
        asyncio.run(self.ks.manual_halt("Test"))
        self.assertTrue(self.ks.is_triggered)

        asyncio.run(self.ks.manual_reset())
        self.assertFalse(self.ks.is_triggered)
        self.assertEqual(self.ks.state, KillSwitchState.DISARMED)

    def test_callback(self):
        """Callback fired on trigger."""
        events = []
        self.ks.on_trigger(lambda e: events.append(e))

        asyncio.run(self.ks.arm())
        asyncio.run(self.ks.manual_halt("Test callback"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].trigger, KillSwitchTrigger.MANUAL)

    def test_status(self):
        """Status report."""
        status = self.ks.get_status()
        self.assertIn("state", status)
        self.assertIn("config", status)
        self.assertEqual(status["state"], "DISARMED")

    def test_disarmed_blocks_trades(self):
        """Disarmed kill switch blocks all trades."""
        # Not armed
        allowed = asyncio.run(self.ks.check_trade(portfolio_value=100000, trade_pnl=0))
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
