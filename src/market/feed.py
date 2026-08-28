"""Real-time market data feed manager.

Aggregates multiple market data connectors, provides unified
streaming, and handles symbol routing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable

from market.connectors.base import ConnectorState, FeedStatistics, MarketDataConnector, PriceTick


@dataclass
class FeedState:
    """Current state of the feed manager."""

    connectors: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    active: bool = False


class FeedManager:
    """Manages multiple market data connectors.

    Provides unified symbol subscription, aggregated streaming,
    and failover between connectors.
    """

    def __init__(self, buffer_size: int = 10000):
        """Initialize feed manager.

        Args:
            buffer_size: Max aggregated tick buffer.
        """
        self._connectors: dict[str, MarketDataConnector] = {}
        self._primary: str | None = None
        self._buffer_size = buffer_size
        self._queue: asyncio.Queue[PriceTick] = asyncio.Queue(maxsize=buffer_size)
        self._callbacks: list[Callable[[PriceTick], None]] = []
        self._running = False
        self._forward_task: asyncio.Task | None = None

    def register_connector(self, connector: MarketDataConnector, primary: bool = False) -> None:
        """Register a market data connector.

        Args:
            connector: Connector instance.
            primary: Whether this is the primary connector.
        """
        self._connectors[connector.name] = connector
        if primary or self._primary is None:
            self._primary = connector.name

        # Forward ticks from this connector to our queue
        connector.add_callback(self._on_tick)

    def add_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Register a callback for all ticks."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _on_tick(self, tick: PriceTick) -> None:
        """Internal tick handler — queues tick and notifies callbacks."""
        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception:
                pass
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            pass

    async def connect(self) -> bool:
        """Connect all registered connectors.

        Returns:
            True if primary connector connected successfully.
        """
        if not self._connectors:
            return False

        self._running = True

        # Connect all connectors
        for name, connector in self._connectors.items():
            ok = await connector.connect()
            if name == self._primary and not ok:
                return False

        # Start forwarding task
        self._forward_task = asyncio.create_task(self._forward_loop())
        return True

    async def disconnect(self) -> None:
        """Disconnect all connectors."""
        self._running = False
        if self._forward_task:
            self._forward_task.cancel()
            try:
                await self._forward_task
            except asyncio.CancelledError:
                pass
            self._forward_task = None

        for connector in self._connectors.values():
            await connector.disconnect()

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols across all connectors.

        Args:
            symbols: List of ticker symbols.
        """
        for connector in self._connectors.values():
            await connector.subscribe(symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from symbols."""
        for connector in self._connectors.values():
            await connector.unsubscribe(symbols)

    async def stream(self) -> AsyncIterator[PriceTick]:
        """Async iterator over all aggregated ticks.

        Yields:
            PriceTick from any active connector.
        """
        while self._running:
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield tick
            except asyncio.TimeoutError:
                continue

    def get_state(self) -> FeedState:
        """Get current feed state."""
        return FeedState(
            connectors=list(self._connectors.keys()),
            symbols=list(
                set().union(
                    *[c.subscribed_symbols for c in self._connectors.values()]
                )
            ),
            active=self._running,
        )

    def get_statistics(self) -> dict[str, FeedStatistics]:
        """Get statistics from all connectors."""
        return {
            name: connector.statistics for name, connector in self._connectors.items()
        }

    async def _forward_loop(self) -> None:
        """Background task that maintains connector health."""
        while self._running:
            # Check connector health and reconnect if needed
            for name, connector in self._connectors.items():
                if connector.state == ConnectorState.ERROR and name == self._primary:
                    # Try to reconnect primary
                    await connector.connect()
            await asyncio.sleep(5.0)

    def __enter__(self):
        """Synchronous context manager entry."""
        return self

    def __exit__(self, *args):
        """Synchronous context manager exit."""
        if self._running:
            asyncio.run(self.disconnect())
