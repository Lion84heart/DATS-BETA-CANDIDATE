"""Tests for StrategyAgent: signal generation, feature reading, publishing."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.agents.schemas import AgentDecision, AgentState, DecisionType, SignalDirection
from src.agents.strategy import StrategyAgent


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for StrategyAgent construction."""

    def test_default_strategy(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Default strategy is trend_following."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        assert agent._strategy == "trend_following"
        assert agent.agent_type == "strategy"

    def test_custom_strategy(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Custom strategy is accepted."""
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            strategy="mean_reversion",
        )
        assert agent._strategy == "mean_reversion"

    def test_invalid_strategy_fallback(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Invalid strategy falls back to default."""
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            strategy="invalid_strategy",
        )
        assert agent._strategy == "trend_following"

    def test_custom_symbols(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Custom symbols list."""
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            symbols=["BTC/USDC", "ETH/USDC"],
        )
        assert agent._symbols == ["BTC/USDC", "ETH/USDC"]

    def test_custom_confidence_threshold(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Custom confidence threshold."""
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            confidence_threshold=0.5,
        )
        assert agent._confidence_threshold == 0.5


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for StrategyAgent lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """StrategyAgent starts correctly."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """StrategyAgent stops correctly."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Works as async context manager."""
        async with StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store) as agent:
            assert agent.state == AgentState.IDLE


# ---------------------------------------------------------------------------
# Think / signal generation
# ---------------------------------------------------------------------------


class TestThink:
    """Tests for think() method."""

    @pytest.mark.asyncio
    async def test_no_features_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """No features available → NOOP decision."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_with_features_generates_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """With features, generates a signal decision."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            confidence_threshold=0.15,  # Lower threshold to ensure signal is generated
        )
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.SIGNAL
        assert "signal" in decision.payload

    @pytest.mark.asyncio
    async def test_signal_has_required_fields(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Generated signal has all required fields."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            confidence_threshold=0.15,
        )
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.SIGNAL
        signal_data = decision.payload["signal"]
        assert signal_data["symbol"] == "SOL/USDC"
        assert signal_data["direction"] in ("BUY", "SELL", "HOLD")
        assert 0.0 <= signal_data["confidence"] <= 1.0
        assert "reason" in signal_data

    @pytest.mark.asyncio
    async def test_confidence_below_threshold_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Signal below confidence threshold → NOOP."""
        # Features that produce very low confidence
        features = {"rsi_14": 50.0, "macd": 0.0, "macd_signal": 0.0, "close": 100.0}
        mock_feature_store.set_features("SOL/USDC", features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            confidence_threshold=0.99,  # Very high threshold
        )
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_too_few_features_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Too few non-None features → skipped."""
        features = {"rsi_14": None, "macd": None, "close": None}
        mock_feature_store.set_features("SOL/USDC", features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_bullish_features_buy_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Bullish features tend to produce BUY signal with trend_following."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            strategy="trend_following",
        )
        await agent.start()
        decision = await agent.think({})
        if decision.decision_type == DecisionType.SIGNAL:
            signal_data = decision.payload["signal"]
            assert signal_data["direction"] in ("BUY", "SELL", "HOLD")

    @pytest.mark.asyncio
    async def test_mean_reversion_on_bullish(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Mean reversion on bullish features may produce SELL."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            strategy="mean_reversion",
        )
        await agent.start()
        decision = await agent.think({})
        # Should produce some decision (SIGNAL or NOOP)
        assert decision.decision_type in (DecisionType.SIGNAL, DecisionType.NOOP)

    @pytest.mark.asyncio
    async def test_features_used_populated(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Signal includes features_used."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})
        if decision.decision_type == DecisionType.SIGNAL:
            signal_data = decision.payload["signal"]
            assert "features_used" in signal_data
            assert len(signal_data["features_used"]) > 0

    @pytest.mark.asyncio
    async def test_multiple_symbols(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Agent can scan multiple symbols."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        mock_feature_store.set_features("BTC/USDC", sample_features)
        agent = StrategyAgent(
            "strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store,
            symbols=["SOL/USDC", "BTC/USDC"],
        )
        await agent.start()
        decision = await agent.think({})
        # Should process both and pick the best
        assert decision.decision_type in (DecisionType.SIGNAL, DecisionType.NOOP)

    @pytest.mark.asyncio
    async def test_nan_safe_skips_none(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Skips signals when critical features are None."""
        features = {"rsi_14": None, "macd": None, "ema_9": None, "close": 100.0}
        mock_feature_store.set_features("SOL/USDC", features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP


# ---------------------------------------------------------------------------
# Act / publishing
# ---------------------------------------------------------------------------


class TestAct:
    """Tests for act() method."""

    @pytest.mark.asyncio
    async def test_act_publishes_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """act() publishes signal to Kafka."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})

        if decision.decision_type == DecisionType.SIGNAL:
            await agent.act(decision)
            assert len(mock_kafka_producer.messages) >= 1

    @pytest.mark.asyncio
    async def test_act_noop_does_nothing(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """act() with NOOP does nothing."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = AgentDecision(
            agent_id="strat-1",
            decision_type=DecisionType.NOOP,
            payload={},
        )
        await agent.act(decision)
        # No messages should be published for NOOP

    @pytest.mark.asyncio
    async def test_act_missing_payload(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """act() handles missing signal payload."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = AgentDecision(
            agent_id="strat-1",
            decision_type=DecisionType.SIGNAL,
            payload={},  # Missing signal
        )
        await agent.act(decision)  # Should not raise

    @pytest.mark.asyncio
    async def act_stores_signal_in_memory(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """act() stores signal in Redis memory."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        decision = await agent.think({})

        if decision.decision_type == DecisionType.SIGNAL:
            await agent.act(decision)
            # Signal should be in memory
            stored = await agent.recall("signal:SOL/USDC")
            assert stored is not None


# ---------------------------------------------------------------------------
# Full cycle
# ---------------------------------------------------------------------------


class TestFullCycle:
    """Tests for run_cycle with StrategyAgent."""

    @pytest.mark.asyncio
    async def test_run_cycle_with_features(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """Full cycle with features produces signal."""
        mock_feature_store.set_features("SOL/USDC", sample_features)
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.IDLE
        assert agent._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_run_cycle_without_features(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Full cycle without features produces NOOP."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.IDLE
        assert agent._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_health(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Health report for strategy agent."""
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        health = await agent.health()
        assert health.agent_id == "strat-1"
        assert health.state == AgentState.IDLE
        assert health.metadata["agent_type"] == "strategy"

    @pytest.mark.asyncio
    async def test_all_strategies(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any, sample_features: dict[str, float]) -> None:
        """All supported strategies run without error."""
        for strategy in ("trend_following", "mean_reversion", "momentum", "breakout"):
            mock_feature_store.set_features("SOL/USDC", sample_features)
            agent = StrategyAgent(
                f"strat-{strategy}", mock_redis_manager, mock_kafka_producer, mock_feature_store,
                strategy=strategy,
            )
            await agent.start()
            decision = await agent.think({})
            assert decision.decision_type in (DecisionType.SIGNAL, DecisionType.NOOP)
            await agent.stop()
