"""Tests for BaseAgent lifecycle, think/act, messaging, memory."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.base import (
    AgentError,
    AgentNotStartedError,
    BaseAgent,
)
from src.agents.schemas import AgentDecision, AgentState


# ---------------------------------------------------------------------------
# Concrete agent for testing
# ---------------------------------------------------------------------------


class TestAgent(BaseAgent):
    """Concrete agent implementation for testing."""

    def __init__(self, agent_id: str, redis_manager: Any, kafka_producer: Any) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="test")
        self.think_calls: int = 0
        self.act_calls: int = 0
        self.last_decision: AgentDecision | None = None

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        self.think_calls += 1
        return AgentDecision(
            agent_id=self.agent_id,
            decision_type="noop",
            payload={"context_keys": list(context.keys())},
        )

    async def act(self, decision: AgentDecision) -> None:
        self.act_calls += 1
        self.last_decision = decision


class FailingThinkAgent(BaseAgent):
    """Agent that fails in think()."""

    def __init__(self, agent_id: str, redis_manager: Any, kafka_producer: Any) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="test")

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        raise RuntimeError("Think failure!")

    async def act(self, decision: AgentDecision) -> None:
        pass


class FailingActAgent(BaseAgent):
    """Agent that fails in act()."""

    def __init__(self, agent_id: str, redis_manager: Any, kafka_producer: Any) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="test")

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        return AgentDecision(
            agent_id=self.agent_id,
            decision_type="noop",
        )

    async def act(self, decision: AgentDecision) -> None:
        raise RuntimeError("Act failure!")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for agent lifecycle (start, stop, health)."""

    @pytest.mark.asyncio
    async def test_start_transitions_to_idle(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """start() transitions agent from INITIALIZING to IDLE."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        assert agent.state == AgentState.INITIALIZING
        await agent.start()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """start() is safe to call multiple times."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.start()  # Should not raise
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop_transitions_to_shutdown(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """stop() transitions agent to SHUTDOWN."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """stop() is safe to call multiple times."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        await agent.stop()  # Should not raise
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Agent works as async context manager."""
        async with TestAgent("test-1", mock_redis_manager, mock_kafka_producer) as agent:
            assert agent.state == AgentState.IDLE
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_agent_attributes(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Agent has correct attributes."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        assert agent.agent_id == "test-1"
        assert agent.agent_type == "test"

    @pytest.mark.asyncio
    async def test_start_stores_metadata(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """start() stores metadata in Redis."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        meta = await agent.recall("metadata")
        assert meta is not None
        assert meta["agent_id"] == "test-1"
        assert meta["agent_type"] == "test"

    @pytest.mark.asyncio
    async def test_stop_stores_metadata(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """stop() updates metadata in Redis."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        meta = await agent.recall("metadata")
        assert meta is not None
        assert meta["state"] == "shutdown"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    """Tests for agent health reporting."""

    @pytest.mark.asyncio
    async def test_health_before_start(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health before start shows INITIALIZING."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        health = await agent.health()
        assert health.agent_id == "test-1"
        assert health.state == AgentState.INITIALIZING
        assert health.error_count == 0
        assert health.tasks_completed == 0

    @pytest.mark.asyncio
    async def test_health_after_start(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health after start shows IDLE."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        health = await agent.health()
        assert health.state == AgentState.IDLE
        assert health.metadata["agent_type"] == "test"

    @pytest.mark.asyncio
    async def test_health_error_count(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health tracks error count."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        agent._error_count = 3
        health = await agent.health()
        assert health.error_count == 3

    @pytest.mark.asyncio
    async def test_health_tasks_completed(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health tracks tasks completed."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        agent._tasks_completed = 7
        health = await agent.health()
        assert health.tasks_completed == 7


# ---------------------------------------------------------------------------
# Core loop
# ---------------------------------------------------------------------------


class TestCoreLoop:
    """Tests for run_cycle, think, act."""

    @pytest.mark.asyncio
    async def test_run_cycle_calls_think_and_act(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """run_cycle() calls think() then act()."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.think_calls == 1
        assert agent.act_calls == 1
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_run_cycle_multiple(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Multiple run_cycle() calls increment counters."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        for _ in range(3):
            await agent.run_cycle()
        assert agent.think_calls == 3
        assert agent.act_calls == 3
        assert agent._tasks_completed == 3

    @pytest.mark.asyncio
    async def test_run_cycle_not_started_raises(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """run_cycle() before start() raises."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        with pytest.raises(AgentNotStartedError):
            await agent.run_cycle()

    @pytest.mark.asyncio
    async def test_run_cycle_when_shutdown(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """run_cycle() when shutdown does nothing."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        await agent.run_cycle()  # Should not raise
        assert agent.think_calls == 0

    @pytest.mark.asyncio
    async def test_run_cycle_think_error(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Error in think() transitions to ERROR state."""
        agent = FailingThinkAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.ERROR
        assert agent._error_count == 1

    @pytest.mark.asyncio
    async def test_run_cycle_act_error(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Error in act() transitions to ERROR state."""
        agent = FailingActAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.ERROR
        assert agent._error_count == 1

    @pytest.mark.asyncio
    async def test_run_cycle_think_error_records_episode(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Error in think() records an error episode."""
        agent = FailingThinkAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        episodes = await agent._memory.get_episodes("test-1")
        assert len(episodes) >= 1
        assert any(ep.get("event") == "error" for ep in episodes)


# ---------------------------------------------------------------------------
# Communication
# ---------------------------------------------------------------------------


class TestCommunication:
    """Tests for send_message and receive_messages."""

    @pytest.mark.asyncio
    async def test_send_message(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """send_message produces a Kafka message."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.send_message("agent-2", "status", {"health": "ok"})
        assert len(mock_kafka_producer.messages) == 1
        msg = mock_kafka_producer.messages[0]
        assert msg["value"]["from_agent"] == "test-1"
        assert msg["value"]["to_agent"] == "agent-2"

    @pytest.mark.asyncio
    async def test_send_message_error(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """send_message handles Kafka errors gracefully."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        # Force send to fail
        async def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Kafka down")
        mock_kafka_producer.send = fail
        # Should not raise
        await agent.send_message("agent-2", "test", {})

    @pytest.mark.asyncio
    async def test_receive_messages_empty(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """receive_messages with no messages."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        messages = []
        async for msg in agent.receive_messages():
            messages.append(msg)
        assert messages == []

    @pytest.mark.asyncio
    async def test_receive_messages_with_data(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """receive_messages yields published messages."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        # Publish a message to the agent's inbox
        await agent._memory.publish_message(
            f"agent:test-1:inbox",
            {
                "from_agent": "sender",
                "to_agent": "test-1",
                "message_type": "signal",
                "payload": {"key": "value"},
            },
        )
        messages = []
        async for msg in agent.receive_messages():
            messages.append(msg)
        assert len(messages) == 1
        assert messages[0].from_agent == "sender"


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class TestMemory:
    """Tests for remember, recall, forget."""

    @pytest.mark.asyncio
    async def test_remember_and_recall(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Store and retrieve a value."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        result = await agent.remember("mykey", {"data": 42})
        assert result is True

        value = await agent.recall("mykey")
        assert value == {"data": 42}

    @pytest.mark.asyncio
    async def test_recall_missing(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """recall returns None for missing key."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        value = await agent.recall("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_forget(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """forget removes a key."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.remember("delete_me", "value")
        assert await agent.recall("delete_me") == "value"

        deleted = await agent.forget("delete_me")
        assert deleted == 1
        assert await agent.recall("delete_me") is None

    @pytest.mark.asyncio
    async def test_forget_missing(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """forget returns 0 for missing key."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        deleted = await agent.forget("nonexistent")
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_remember_with_ttl(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """remember with custom TTL."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.remember("ttl_key", "value", ttl=60)
        # Key should exist
        value = await agent.recall("ttl_key")
        assert value == "value"

    @pytest.mark.asyncio
    async def test_memory_namespaced(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Memory is namespaced by agent_id."""
        agent1 = TestAgent("agent-a", mock_redis_manager, mock_kafka_producer)
        agent2 = TestAgent("agent-b", mock_redis_manager, mock_kafka_producer)
        await agent1.start()
        await agent2.start()

        await agent1.remember("shared_key", "agent-a-value")
        await agent2.remember("shared_key", "agent-b-value")

        assert await agent1.recall("shared_key") == "agent-a-value"
        assert await agent2.recall("shared_key") == "agent-b-value"

    @pytest.mark.asyncio
    async def test_remember_failure(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """remember returns False on failure."""
        async def fail(*args: Any, **kwargs: Any) -> bool:
            return False
        mock_redis_manager.set = fail
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        result = await agent.remember("key", "value")
        assert result is False

    @pytest.mark.asyncio
    async def test_recall_failure(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """recall returns None on failure."""
        async def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Redis error")
        mock_redis_manager.get = fail
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        value = await agent.recall("key")
        assert value is None

    @pytest.mark.asyncio
    async def test_forget_failure(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """forget returns 0 on failure."""
        async def fail(*args: Any, **kwargs: Any) -> int:
            raise RuntimeError("Redis error")
        mock_redis_manager.delete = fail
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        result = await agent.forget("key")
        assert result == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and state transitions."""

    @pytest.mark.asyncio
    async def test_error_count_incremented(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Error count increments on failures."""
        agent = FailingThinkAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent._error_count == 1
        await agent.run_cycle()
        assert agent._error_count == 2

    @pytest.mark.asyncio
    async def test_state_error_after_failure(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """State becomes ERROR after think failure."""
        agent = FailingThinkAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assert agent.state == AgentState.IDLE
        await agent.run_cycle()
        assert agent.state == AgentState.ERROR

    @pytest.mark.asyncio
    async def test_last_active_updated(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """last_active is updated during run_cycle."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        before = agent._last_active
        await agent.run_cycle()
        assert agent._last_active >= before

    @pytest.mark.asyncio
    async def test_context_has_agent_info(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Context contains agent metadata."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.last_decision is not None
        payload = agent.last_decision.payload
        assert "agent_id" not in payload  # Context keys, not values
        assert "context_keys" in payload


# ---------------------------------------------------------------------------
# Decision flow
# ---------------------------------------------------------------------------


class TestDecisionFlow:
    """Tests for the decision passing from think to act."""

    @pytest.mark.asyncio
    async def test_decision_passed_to_act(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Decision from think() is passed to act()."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.last_decision is not None
        assert agent.last_decision.agent_id == "test-1"

    @pytest.mark.asyncio
    async def test_tasks_completed_after_cycle(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """tasks_completed increments after successful cycle."""
        agent = TestAgent("test-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assert agent._tasks_completed == 0
        await agent.run_cycle()
        assert agent._tasks_completed == 1
