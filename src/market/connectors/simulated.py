"""Simulated market data connector for paper trading.

Uses the MarketSimulator to generate synthetic price ticks
for testing and paper trading without real market data.
"""

from __future__ import annotations

import asyncio
import time

from simulation.market_sim import MarketSimulator

from market.connectors.base import MarketDataConnector, PriceTick


class SimulatedConnector(MarketDataConnector):
    """Simulated market data connector using MarketSimulator.

    Generates synthetic price ticks via GBM for paper trading
    and testing without real market data access.
    """

    def __init__(
        self,
        seed: int = 42,
        tick_interval: float = 1.0,
        buffer_size: int = 1000,
    ):
        """Initialize simulated connector.

        Args:
            seed: Random seed for reproducible paths.
            tick_interval: Seconds between synthetic ticks.
            buffer_size: Tick buffer size.
        """
        super().__init__(name="simulated", buffer_size=buffer_size)
        self._simulator = MarketSimulator(seed=seed)
        self._tick_interval = tick_interval
        self._seed = seed
        self._prices: dict[str, float] = {}
        self._initial_prices: dict[str, float] = {}

    def configure_symbol(self, symbol: str, initial_price: float) -> None:
        """Configure initial price for a symbol.

        Args:
            symbol: Ticker symbol.
            initial_price: Starting price.
        """
        self._initial_prices[symbol] = initial_price
        self._prices[symbol] = initial_price

    async def _connect_impl(self) -> bool:
        """Simulated connection always succeeds."""
        return True

    async def _disconnect_impl(self) -> None:
        """Simulated disconnection is a no-op."""
        pass

    async def _subscribe_impl(self, symbols: list[str]) -> None:
        """Set up initial prices for new symbols."""
        for symbol in symbols:
            if symbol not in self._initial_prices:
                # Default initial price if not configured
                self._initial_prices[symbol] = 100.0
                self._prices[symbol] = 100.0

    async def _unsubscribe_impl(self, symbols: list[str]) -> None:
        """Remove symbols from price tracking."""
        for symbol in symbols:
            self._prices.pop(symbol, None)

    async def _poll_impl(self) -> None:
        """Generate synthetic ticks for all subscribed symbols."""
        if not self._subscribed:
            await asyncio.sleep(self._tick_interval)
            return

        for symbol in self._subscribed:
            if symbol not in self._prices:
                self._prices[symbol] = self._initial_prices.get(symbol, 100.0)

            # Generate a small random step
            current = self._prices[symbol]
            # Use simulator to generate a short path
            path = self._simulator.generate_path(symbol, current, 2)
            new_price = path.prices[-1]
            self._prices[symbol] = new_price

            # Create synthetic tick
            spread = new_price * 0.001  # 0.1% spread
            tick = PriceTick(
                symbol=symbol,
                timestamp=time.time(),
                price=new_price,
                bid=new_price - spread / 2,
                ask=new_price + spread / 2,
                volume=1000.0,  # Synthetic volume
                source="simulated",
            )
            self._notify(tick)

        await asyncio.sleep(self._tick_interval)

    def is_available(self) -> bool:
        """Simulated connector is always available."""
        return True

    def reset(self) -> None:
        """Reset simulator state for reproducible testing."""
        self._simulator = MarketSimulator(seed=self._seed)
        self._prices.clear()
        self._prices.update(self._initial_prices)
