"""Tests for the hot-swap strategy registry."""

from __future__ import annotations

import pickle

import pytest

from src.trading.hotswap import StrategyRegistry
from src.trading.schemas import StrategyConfig, StrategyType
from src.trading.strategies.trend_following import TrendFollowingStrategy
from tests.trading.conftest import MockStrategy


class TestStrategyRegistryBasic:
    """Tests for basic registry operations."""

    @pytest.mark.asyncio
    async def test_register_strategy(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        assert "trend" in registry
        assert len(registry) == 1

    @pytest.mark.asyncio
    async def test_unregister_strategy(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        await registry.unregister("trend")
        assert "trend" not in registry
        assert len(registry) == 0

    @pytest.mark.asyncio
    async def test_get_strategy(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        retrieved = await registry.get("trend")
        assert retrieved is not None
        assert retrieved.name == "trend_following"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self) -> None:
        registry = StrategyRegistry()
        result = await registry.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_strategies(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        strategies = await registry.list_strategies()
        assert len(strategies) == 1
        assert strategies[0]["name"] == "trend"
        assert strategies[0]["type"] == "trend_following"

    @pytest.mark.asyncio
    async def test_register_duplicate_raises(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        with pytest.raises(ValueError, match="already registered"):
            await registry.register("trend", strategy)


class TestStrategyRegistryEnableDisable:
    """Tests for enabling/disabling strategies."""

    @pytest.mark.asyncio
    async def test_enable_strategy(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        await registry.disable("trend")
        assert await registry.is_enabled("trend") is False
        await registry.enable("trend")
        assert await registry.is_enabled("trend") is True

    @pytest.mark.asyncio
    async def test_disable_nonexistent_raises(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(ValueError):
            await registry.disable("nonexistent")

    @pytest.mark.asyncio
    async def test_is_enabled_nonexistent(self) -> None:
        registry = StrategyRegistry()
        result = await registry.is_enabled("nonexistent")
        assert result is False


class TestStrategyRegistryHotSwap:
    """Tests for hot-swap parameter updates."""

    @pytest.mark.asyncio
    async def test_update_parameters(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"fast_ema": 9.0, "slow_ema": 21.0},
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        success = await registry.update_parameters("trend", {"fast_ema": 15.0})
        assert success is True
        updated = await registry.get("trend")
        assert updated is not None
        assert updated.get_parameters()["fast_ema"] == 15.0

    @pytest.mark.asyncio
    async def test_update_parameters_clamped(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        await registry.update_parameters("trend", {"fast_ema": 100.0})
        updated = await registry.get("trend")
        assert updated is not None
        assert updated.get_parameters()["fast_ema"] == 50.0  # clamped to max

    @pytest.mark.asyncio
    async def test_update_unknown_strategy_raises(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(ValueError, match="not found"):
            await registry.update_parameters("nonexistent", {"fast_ema": 10.0})

    @pytest.mark.asyncio
    async def test_update_unknown_parameter_raises(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        with pytest.raises(ValueError, match="Unknown parameter"):
            await registry.update_parameters("trend", {"unknown": 10.0})


class TestStrategyRegistryHealth:
    """Tests for health checks."""

    @pytest.mark.asyncio
    async def test_health(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        health = await registry.health()
        assert "trend" in health

    @pytest.mark.asyncio
    async def test_strategy_health_in_list(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        strategies = await registry.list_strategies()
        assert "health" in strategies[0]


class TestStrategyRegistrySerialization:
    """Tests for pickle serialization."""

    @pytest.mark.asyncio
    async def test_serialize_deserialize(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"fast_ema": 15.0},
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        await registry.disable("trend")

        serialized = registry.serialize()
        assert isinstance(serialized, bytes)

        new_registry = StrategyRegistry()
        new_registry.deserialize(serialized)
        assert "trend" in new_registry
        assert len(new_registry) == 1
        assert await new_registry.is_enabled("trend") is False

    @pytest.mark.asyncio
    async def test_deserialize_preserves_parameters(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
            parameters={"fast_ema": 20.0, "slow_ema": 50.0},
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)

        serialized = registry.serialize()
        new_registry = StrategyRegistry()
        new_registry.deserialize(serialized)

        strategy = await new_registry.get("trend")
        assert strategy is not None
        assert strategy.get_parameters()["fast_ema"] == 20.0

    def test_get_strategy_states(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        # Can't use async in non-async test, register manually
        registry._strategies["trend"] = strategy
        registry._enabled["trend"] = True
        states = registry.get_strategy_states()
        assert "trend" in states
        assert states["trend"].name == "trend_following"


class TestStrategyRegistryLen:
    """Tests for registry length."""

    def test_empty_registry(self) -> None:
        registry = StrategyRegistry()
        assert len(registry) == 0

    @pytest.mark.asyncio
    async def test_nonempty_registry(self) -> None:
        registry = StrategyRegistry()
        config = StrategyConfig(
            strategy_type=StrategyType.TREND_FOLLOWING,
            symbol="SOL/USDC",
        )
        strategy = TrendFollowingStrategy(config)
        await registry.register("trend", strategy)
        assert len(registry) == 1
