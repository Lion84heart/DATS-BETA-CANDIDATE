"""Kill switch / circuit breaker for emergency risk control.

Implements automatic trading halt based on configurable triggers:
- Maximum drawdown limit
- Daily loss limit
- Consecutive loss limit
- Volatility spike detection
- Manual override
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


class KillSwitchState(Enum):
    """State of the kill switch."""

    ARMED = auto()      # Monitoring, trading allowed
    TRIGGERED = auto()  # Kill switch activated, trading halted
    MANUAL_HALT = auto()  # Manually halted
    DISARMED = auto()   # Not monitoring


class KillSwitchTrigger(Enum):
    """Reason for kill switch activation."""

    MAX_DRAWDOWN = auto()
    DAILY_LOSS_LIMIT = auto()
    CONSECUTIVE_LOSSES = auto()
    VOLATILITY_SPIKE = auto()
    MANUAL = auto()
    MARGIN_CALL = auto()


@dataclass
class KillSwitchConfig:
    """Configuration for kill switch triggers."""

    max_drawdown_pct: float = 0.10          # 10% max drawdown
    daily_loss_limit_pct: float = 0.05      # 5% daily loss limit
    consecutive_losses: int = 5             # Halt after N consecutive losses
    volatility_spike_multiplier: float = 3.0  # Halt if vol spikes 3x average
    cooldown_seconds: int = 300             # 5 minute cooldown before re-arm
    auto_rearm: bool = False                # Whether to auto-rearm after cooldown


@dataclass
class KillSwitchEvent:
    """Record of a kill switch activation."""

    timestamp: float
    trigger: KillSwitchTrigger
    reason: str
    portfolio_value: float
    pnl_at_trigger: float


class KillSwitch:
    """Circuit breaker that halts trading when risk thresholds are breached.

    Thread-safe async implementation suitable for high-frequency trading.
    """

    def __init__(self, config: KillSwitchConfig | None = None):
        """Initialize kill switch.

        Args:
            config: KillSwitchConfig with trigger thresholds.
        """
        self.config = config or KillSwitchConfig()
        self.state = KillSwitchState.DISARMED
        self._lock = asyncio.Lock()
        self._events: list[KillSwitchEvent] = []
        self._daily_pnl = 0.0
        self._consecutive_loss_count = 0
        self._peak_portfolio_value = 0.0
        self._triggered_at = 0.0
        self._volatility_history: list[float] = []
        self._callbacks: list[Callable[[KillSwitchEvent], None]] = []

    async def arm(self) -> None:
        """Arm the kill switch (start monitoring)."""
        async with self._lock:
            if self.state == KillSwitchState.TRIGGERED:
                # Check cooldown
                elapsed = time.time() - self._triggered_at
                if elapsed < self.config.cooldown_seconds:
                    remaining = self.config.cooldown_seconds - elapsed
                    raise RuntimeError(f"Kill switch in cooldown: {remaining:.0f}s remaining")
                if not self.config.auto_rearm:
                    raise RuntimeError("Kill switch must be manually reset")
            self.state = KillSwitchState.ARMED
            self._daily_pnl = 0.0
            self._consecutive_loss_count = 0
            self._volatility_history.clear()

    async def disarm(self) -> None:
        """Disarm the kill switch (stop monitoring)."""
        async with self._lock:
            self.state = KillSwitchState.DISARMED

    async def manual_halt(self, reason: str = "Manual halt") -> KillSwitchEvent:
        """Manually trigger the kill switch.

        Args:
            reason: Human-readable reason for halt.

        Returns:
            KillSwitchEvent record.
        """
        async with self._lock:
            return self._trigger(KillSwitchTrigger.MANUAL, reason, 0.0, 0.0)

    async def manual_reset(self) -> None:
        """Manually reset the kill switch after trigger."""
        async with self._lock:
            self.state = KillSwitchState.DISARMED
            self._daily_pnl = 0.0
            self._consecutive_loss_count = 0

    async def check_trade(
        self,
        portfolio_value: float,
        trade_pnl: float,
        volatility: float | None = None,
    ) -> bool:
        """Check if a trade should be allowed.

        Args:
            portfolio_value: Current portfolio value.
            trade_pnl: P&L from the most recent trade.
            volatility: Current volatility estimate (optional).

        Returns:
            True if trading is allowed, False if kill switch is triggered.
        """
        async with self._lock:
            if self.state != KillSwitchState.ARMED:
                return False

            # Update tracking
            self._daily_pnl += trade_pnl
            if profit := trade_pnl > 0:
                self._consecutive_loss_count = 0
            else:
                self._consecutive_loss_count += 1

            # Update peak and drawdown
            if portfolio_value > self._peak_portfolio_value:
                self._peak_portfolio_value = portfolio_value

            drawdown = (self._peak_portfolio_value - portfolio_value) / self._peak_portfolio_value if self._peak_portfolio_value > 0 else 0.0

            # Check triggers
            if drawdown >= self.config.max_drawdown_pct:
                self._trigger(
                    KillSwitchTrigger.MAX_DRAWDOWN,
                    f"Drawdown {drawdown:.2%} exceeded limit {self.config.max_drawdown_pct:.2%}",
                    portfolio_value,
                    self._daily_pnl,
                )
                return False

            if self._daily_pnl < 0 and abs(self._daily_pnl) / portfolio_value >= self.config.daily_loss_limit_pct:
                self._trigger(
                    KillSwitchTrigger.DAILY_LOSS_LIMIT,
                    f"Daily loss {abs(self._daily_pnl):.2f} exceeded limit {portfolio_value * self.config.daily_loss_limit_pct:.2f}",
                    portfolio_value,
                    self._daily_pnl,
                )
                return False

            if self._consecutive_loss_count >= self.config.consecutive_losses:
                self._trigger(
                    KillSwitchTrigger.CONSECUTIVE_LOSSES,
                    f"{self._consecutive_loss_count} consecutive losses",
                    portfolio_value,
                    self._daily_pnl,
                )
                return False

            if volatility is not None:
                self._volatility_history.append(volatility)
                if len(self._volatility_history) >= 20:
                    avg_vol = sum(self._volatility_history[-20:]) / 20
                    if avg_vol > 0 and volatility / avg_vol >= self.config.volatility_spike_multiplier:
                        self._trigger(
                            KillSwitchTrigger.VOLATILITY_SPIKE,
                            f"Volatility spike: {volatility:.4f} vs avg {avg_vol:.4f}",
                            portfolio_value,
                            self._daily_pnl,
                        )
                        return False

            return True

    def _trigger(
        self,
        trigger: KillSwitchTrigger,
        reason: str,
        portfolio_value: float,
        pnl: float,
    ) -> KillSwitchEvent:
        """Internal trigger (must hold lock)."""
        self.state = KillSwitchState.TRIGGERED
        self._triggered_at = time.time()
        event = KillSwitchEvent(
            timestamp=time.time(),
            trigger=trigger,
            reason=reason,
            portfolio_value=portfolio_value,
            pnl_at_trigger=pnl,
        )
        self._events.append(event)
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass
        return event

    def on_trigger(self, callback: Callable[[KillSwitchEvent], None]) -> None:
        """Register a callback to be called when kill switch triggers."""
        self._callbacks.append(callback)

    @property
    def is_armed(self) -> bool:
        """Return True if kill switch is armed and monitoring."""
        return self.state == KillSwitchState.ARMED

    @property
    def is_triggered(self) -> bool:
        """Return True if kill switch has been triggered."""
        return self.state == KillSwitchState.TRIGGERED

    @property
    def event_history(self) -> list[KillSwitchEvent]:
        """Return history of kill switch events."""
        return self._events.copy()

    def get_status(self) -> dict:
        """Return current kill switch status."""
        return {
            "state": self.state.name,
            "daily_pnl": self._daily_pnl,
            "consecutive_losses": self._consecutive_loss_count,
            "peak_value": self._peak_portfolio_value,
            "events_triggered": len(self._events),
            "config": {
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "daily_loss_limit_pct": self.config.daily_loss_limit_pct,
                "consecutive_losses": self.config.consecutive_losses,
                "cooldown_seconds": self.config.cooldown_seconds,
                "auto_rearm": self.config.auto_rearm,
            },
        }
