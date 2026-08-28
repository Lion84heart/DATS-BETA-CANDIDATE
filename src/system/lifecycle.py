"""DATS System Lifecycle Management (M10).

Production-ready startup, shutdown, and signal handling
for graceful degradation and resource cleanup.
"""

from __future__ import annotations

import asyncio
import signal
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Callable


class SystemState(Enum):
    """Lifecycle states of the trading system."""

    INITIALIZING = auto()
    STARTING = auto()
    RUNNING = auto()
    DEGRADED = auto()
    STOPPING = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class LifecycleEvent:
    """A lifecycle transition event."""

    from_state: SystemState
    to_state: SystemState
    timestamp: float
    reason: str = ""


class SystemLifecycle:
    """Manages the complete lifecycle of the DATS trading system.

    Handles initialization, startup, running, graceful shutdown,
    and signal-based termination. Supports registered cleanup hooks.
    """

    def __init__(self):
        self._state = SystemState.INITIALIZING
        self._transitions: list[LifecycleEvent] = []
        self._startup_hooks: list[Callable[[], Any]] = []
        self._shutdown_hooks: list[Callable[[], Any]] = []
        self._degraded_hooks: list[Callable[[], Any]] = []
        self._start_time: float = 0.0
        self._shutdown_event: asyncio.Event | None = None
        self._shutdown_requested = False

    @property
    def state(self) -> SystemState:
        """Current system state."""
        return self._state

    @property
    def uptime_seconds(self) -> float:
        """Seconds since system started."""
        if self._start_time == 0.0:
            return 0.0
        return time.time() - self._start_time

    @property
    def is_running(self) -> bool:
        """True if system is in RUNNING or DEGRADED state."""
        return self._state in (SystemState.RUNNING, SystemState.DEGRADED)

    @property
    def is_shutting_down(self) -> bool:
        """True if shutdown has been requested."""
        return self._shutdown_requested

    def on_startup(self, hook: Callable[[], Any]) -> Callable[[], Any]:
        """Register a startup hook.

        Hooks are executed in registration order during startup.
        """
        self._startup_hooks.append(hook)
        return hook

    def on_shutdown(self, hook: Callable[[], Any]) -> Callable[[], Any]:
        """Register a shutdown hook.

        Hooks are executed in reverse registration order during shutdown.
        """
        self._shutdown_hooks.append(hook)
        return hook

    def on_degraded(self, hook: Callable[[], Any]) -> Callable[[], Any]:
        """Register a degraded mode hook."""
        self._degraded_hooks.append(hook)
        return hook

    def transition(self, new_state: SystemState, reason: str = "") -> None:
        """Transition to a new lifecycle state.

        Args:
            new_state: Target state.
            reason: Reason for transition.
        """
        old = self._state
        self._state = new_state
        self._transitions.append(
            LifecycleEvent(
                from_state=old,
                to_state=new_state,
                timestamp=time.time(),
                reason=reason,
            )
        )

    async def start(self) -> bool:
        """Execute startup sequence.

        Returns:
            True if startup succeeded.
        """
        if self._state != SystemState.INITIALIZING:
            return False

        self.transition(SystemState.STARTING, "Startup initiated")

        for hook in self._startup_hooks:
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                self.transition(SystemState.ERROR, f"Startup hook failed: {e}")
                return False

        self._start_time = time.time()
        self.transition(SystemState.RUNNING, "All startup hooks completed")
        return True

    async def stop(self, reason: str = "Manual stop") -> None:
        """Execute graceful shutdown sequence.

        Args:
            reason: Reason for shutdown.
        """
        if self._state in (SystemState.STOPPING, SystemState.STOPPED):
            return

        self._shutdown_requested = True
        self.transition(SystemState.STOPPING, reason)

        # Execute shutdown hooks in reverse order (LIFO)
        for hook in reversed(self._shutdown_hooks):
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Continue cleanup even if one hook fails

        self.transition(SystemState.STOPPED, "Shutdown complete")

    def request_shutdown(self, reason: str = "Shutdown requested") -> None:
        """Request shutdown (thread-safe, non-blocking).

        Args:
            reason: Reason for shutdown.
        """
        self._shutdown_requested = True
        if self._shutdown_event:
            self._shutdown_event.set()
        self.transition(SystemState.STOPPING, reason)

    def install_signal_handlers(self) -> None:
        """Install OS signal handlers for graceful shutdown.

        Handles SIGTERM and SIGINT for Docker/containerized environments.
        """
        def _handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            self.request_shutdown(f"Received {sig_name}")

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

    def get_transitions(self) -> list[LifecycleEvent]:
        """Get all lifecycle transitions."""
        return self._transitions.copy()

    def get_state_history(self) -> list[tuple[float, SystemState, str]]:
        """Get state history as (timestamp, state, reason) tuples."""
        return [(t.timestamp, t.to_state, t.reason) for t in self._transitions]

    def to_dict(self) -> dict[str, Any]:
        """Serialize current state."""
        return {
            "state": self._state.name,
            "uptime_seconds": self.uptime_seconds,
            "is_running": self.is_running,
            "is_shutting_down": self.is_shutting_down,
            "startup_hooks": len(self._startup_hooks),
            "shutdown_hooks": len(self._shutdown_hooks),
            "transitions": [
                {
                    "from": t.from_state.name,
                    "to": t.to_state.name,
                    "timestamp": t.timestamp,
                    "reason": t.reason,
                }
                for t in self._transitions
            ],
        }
