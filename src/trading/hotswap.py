"""DATS — Hot-Swap Strategy Registry.

Enables dynamic strategy registration, parameter updates, and lifecycle
management without restarting the trading system.
"""

from __future__ import annotations

import logging
import pickle
from typing import Any

from trading.base_strategy import BaseStrategy
from trading.schemas import StrategyState

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """Registry for hot-swapping strategies without restart.

    Maintains a mapping of strategy name -> strategy instance.
    Supports pickle serialization for state persistence across swaps.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, BaseStrategy] = {}
        self._enabled: dict[str, bool] = {}

    async def register(self, name: str, strategy: BaseStrategy) -> None:
        """Register a strategy.

        Args:
            name: Unique strategy name.
            strategy: Strategy instance.

        Raises:
            ValueError: If name is already registered.
        """
        if name in self._strategies:
            raise ValueError(f"Strategy '{name}' is already registered")
        self._strategies[name] = strategy
        self._enabled[name] = True
        await strategy.initialize()
        logger.info("Registered strategy: %s (%s)", name, strategy.strategy_type.value)

    async def unregister(self, name: str) -> None:
        """Unregister and teardown a strategy.

        Args:
            name: Strategy name to unregister.
        """
        if name not in self._strategies:
            return
        strategy = self._strategies[name]
        await strategy.teardown()
        del self._strategies[name]
        if name in self._enabled:
            del self._enabled[name]
        logger.info("Unregistered strategy: %s", name)

    async def get(self, name: str) -> BaseStrategy | None:
        """Get a strategy by name.

        Args:
            name: Strategy name.

        Returns:
            The strategy instance, or None if not found.
        """
        return self._strategies.get(name)

    async def list_strategies(self) -> list[dict[str, Any]]:
        """List all registered strategies with metadata.

        Returns:
            List of dicts with name, type, enabled, and health info.
        """
        result: list[dict[str, Any]] = []
        for name, strategy in self._strategies.items():
            health = await strategy.health()
            result.append({
                "name": name,
                "type": strategy.strategy_type.value,
                "enabled": self._enabled.get(name, True),
                "health": health,
            })
        return result

    async def update_parameters(self, name: str, params: dict[str, float]) -> bool:
        """Hot-swap: update strategy parameters without restart.

        Args:
            name: Strategy name.
            params: New parameter values.

        Returns:
            True if update succeeded.

        Raises:
            ValueError: If strategy not found or parameters invalid.
        """
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' not found in registry")
        strategy = self._strategies[name]
        try:
            strategy.update_parameters(params)
            logger.info("Hot-swapped parameters for %s: %s", name, params)
            return True
        except Exception as exc:
            logger.error("Failed to update parameters for %s: %s", name, exc)
            raise

    async def enable(self, name: str) -> None:
        """Enable a strategy."""
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' not found")
        self._enabled[name] = True
        self._strategies[name]._enabled = True
        logger.info("Enabled strategy: %s", name)

    async def disable(self, name: str) -> None:
        """Disable a strategy."""
        if name not in self._strategies:
            raise ValueError(f"Strategy '{name}' not found")
        self._enabled[name] = False
        self._strategies[name]._enabled = False
        logger.info("Disabled strategy: %s", name)

    async def is_enabled(self, name: str) -> bool:
        """Check if a strategy is enabled."""
        return self._enabled.get(name, False) if name in self._strategies else False

    async def health(self) -> dict[str, dict[str, Any]]:
        """Get health status of all strategies.

        Returns:
            Dict mapping strategy name -> health dict.
        """
        result: dict[str, dict[str, Any]] = {}
        for name, strategy in self._strategies.items():
            result[name] = await strategy.health()
        return result

    def serialize(self) -> bytes:
        """Serialize the entire registry to bytes using pickle.

        Returns:
            Pickled registry state.
        """
        state = {
            "strategies": {
                name: {
                    "pickle": pickle.dumps(strategy),
                    "enabled": self._enabled.get(name, True),
                }
                for name, strategy in self._strategies.items()
            },
        }
        return pickle.dumps(state)

    def deserialize(self, data: bytes) -> None:
        """Restore registry from serialized bytes.

        Args:
            data: Previously serialized registry state.
        """
        state = pickle.loads(data)
        self._strategies = {}
        self._enabled = {}
        for name, info in state["strategies"].items():
            self._strategies[name] = pickle.loads(info["pickle"])
            self._enabled[name] = info.get("enabled", True)
        logger.info("Deserialized %d strategies", len(self._strategies))

    def get_strategy_states(self) -> dict[str, StrategyState]:
        """Get serializable states for all strategies.

        Returns:
            Dict mapping strategy name -> StrategyState.
        """
        return {
            name: strategy.to_strategy_state()
            for name, strategy in self._strategies.items()
        }

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, name: str) -> bool:
        return name in self._strategies
