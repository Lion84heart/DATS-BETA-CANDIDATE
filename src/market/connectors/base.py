"""Market data connector interface.

Abstract base for real-time market data connectors.
Supports async streaming, symbol subscription, and backpressure.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import AsyncIterator, Callable


class ConnectorState(Enum):
    """Lifecycle states of a market data connector."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    SUBSCRIBING = auto()
    STREAMING = auto()
    DISCONNECTING = auto()
    ERROR = auto()


@dataclass(frozen=True)
class PriceTick:
    """A single price tick from a market data source."""

    symbol: str
    timestamp: float
    price: float
    bid: float
    ask: float
    volume: float = 0.0
    source: str = "unknown"


@dataclass(frozen=True)
class Trade:
    """A trade execution from a market data source."""

    symbol: str
    timestamp: float
    price: float
    quantity: float
    side: str  # "buy" or "sell"
    source: str = "unknown"


@dataclass
class FeedStatistics:
    """Statistics for a market data feed."""

    ticks_received: int = 0
    ticks_dropped: int = 0
    last_tick_time: float = 0.0
    reconnections: int = 0
    errors: int = 0
    avg_latency_ms: float = 0.0
    symbols: list[str] = field(default_factory=list)


class MarketDataConnector(ABC):
    """Abstract base for real-time market data connectors.

    Implementations must provide async streaming of PriceTick
    objects for subscribed symbols.
    """

    def __init__(self, name: str, buffer_size: int = 1000):
        """Initialize connector.

        Args:
            name: Connector identifier (e.g. "simulated", "alpaca").
            buffer_size: Max tick buffer before backpressure drops.
        """
        self.name = name
        self._buffer_size = buffer_size
        self._state = ConnectorState.DISCONNECTED
        self._subscribed: set[str] = set()
        self._queue: asyncio.Queue[PriceTick] = asyncio.Queue(maxsize=buffer_size)
        self._callbacks: list[Callable[[PriceTick], None]] = []
        self._stats = FeedStatistics()
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def state(self) -> ConnectorState:
        """Current connector state."""
        return self._state

    @property
    def subscribed_symbols(self) -> set[str]:
        """Currently subscribed symbols."""
        return self._subscribed.copy()

    @property
    def statistics(self) -> FeedStatistics:
        """Feed statistics."""
        return FeedStatistics(
            ticks_received=self._stats.ticks_received,
            ticks_dropped=self._stats.ticks_dropped,
            last_tick_time=self._stats.last_tick_time,
            reconnections=self._stats.reconnections,
            errors=self._stats.errors,
            avg_latency_ms=self._stats.avg_latency_ms,
            symbols=list(self._subscribed),
        )

    def add_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Register a callback for new ticks."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[PriceTick], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols.

        Args:
            symbols: List of ticker symbols.
        """
        self._subscribed.update(symbols)
        await self._subscribe_impl(symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from symbols.

        Args:
            symbols: List of ticker symbols.
        """
        self._subscribed.difference_update(symbols)
        await self._unsubscribe_impl(symbols)

    async def connect(self) -> bool:
        """Connect to the data source.

        Returns:
            True if connected successfully.
        """
        self._state = ConnectorState.CONNECTING
        try:
            ok = await self._connect_impl()
            if ok:
                self._state = ConnectorState.CONNECTED
                self._running = True
                self._task = asyncio.create_task(self._dispatch_loop())
            else:
                self._state = ConnectorState.ERROR
            return ok
        except Exception:
            self._state = ConnectorState.ERROR
            self._stats.errors += 1
            return False

    async def disconnect(self) -> None:
        """Disconnect from the data source."""
        self._running = False
        self._state = ConnectorState.DISCONNECTING
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._disconnect_impl()
        self._state = ConnectorState.DISCONNECTED

    async def stream(self) -> AsyncIterator[PriceTick]:
        """Async iterator over incoming ticks.

        Yields:
            PriceTick objects as they arrive.
        """
        while self._running:
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield tick
            except asyncio.TimeoutError:
                continue

    def _notify(self, tick: PriceTick) -> None:
        """Notify all callbacks and queue of a new tick."""
        self._stats.ticks_received += 1
        self._stats.last_tick_time = tick.timestamp

        for cb in self._callbacks:
            try:
                cb(tick)
            except Exception:
                pass  # Callback errors should not break the feed

        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            self._stats.ticks_dropped += 1

    async def _dispatch_loop(self) -> None:
        """Background task that pulls from source and notifies."""
        try:
            while self._running:
                await self._poll_impl()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._stats.errors += 1
            self._state = ConnectorState.ERROR

    # --- Abstract methods for implementations ---

    @abstractmethod
    async def _connect_impl(self) -> bool:
        """Implementation-specific connection logic."""
        ...

    @abstractmethod
    async def _disconnect_impl(self) -> None:
        """Implementation-specific disconnection logic."""
        ...

    @abstractmethod
    async def _subscribe_impl(self, symbols: list[str]) -> None:
        """Implementation-specific subscription logic."""
        ...

    @abstractmethod
    async def _unsubscribe_impl(self, symbols: list[str]) -> None:
        """Implementation-specific unsubscription logic."""
        ...

    @abstractmethod
    async def _poll_impl(self) -> None:
        """Implementation-specific polling logic.

        Should call self._notify(tick) for each received tick.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this connector is available for use."""
        ...
