"""Tests for AgentMemory (episodic, semantic, working, shared)."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.memory import AgentMemory


# ---------------------------------------------------------------------------
# Episodic memory
# ---------------------------------------------------------------------------


class TestEpisodicMemory:
    """Tests for episodic memory (add_episode, get_episodes, search_episodes)."""

    @pytest.mark.asyncio
    async def test_add_and_get_episode(self, mock_redis_manager: Any) -> None:
        """Add an episode and retrieve it."""
        memory = AgentMemory(mock_redis_manager)
        result = await memory.add_episode("agent-1", {"event": "test", "data": 123})
        assert result is True

        episodes = await memory.get_episodes("agent-1")
        assert len(episodes) == 1
        assert episodes[0]["event"] == "test"
        assert episodes[0]["data"] == 123
        assert "_stored_at" in episodes[0]

    @pytest.mark.asyncio
    async def test_add_episode_includes_agent_id(self, mock_redis_manager: Any) -> None:
        """Episode includes agent_id field."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-1", {"event": "test"})
        episodes = await memory.get_episodes("agent-1")
        assert episodes[0]["_agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_get_episodes_newest_first(self, mock_redis_manager: Any) -> None:
        """Episodes returned newest-first."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-1", {"event": "first"})
        await memory.add_episode("agent-1", {"event": "second"})
        await memory.add_episode("agent-1", {"event": "third"})

        episodes = await memory.get_episodes("agent-1")
        assert len(episodes) == 3
        assert episodes[0]["event"] == "third"
        assert episodes[1]["event"] == "second"
        assert episodes[2]["event"] == "first"

    @pytest.mark.asyncio
    async def test_get_episodes_limit(self, mock_redis_manager: Any) -> None:
        """Limit parameter controls episode count."""
        memory = AgentMemory(mock_redis_manager)
        for i in range(5):
            await memory.add_episode("agent-1", {"event": f"ep-{i}"})

        episodes = await memory.get_episodes("agent-1", limit=3)
        assert len(episodes) == 3
        assert episodes[0]["event"] == "ep-4"

    @pytest.mark.asyncio
    async def test_get_episodes_empty(self, mock_redis_manager: Any) -> None:
        """Empty list for unknown agent."""
        memory = AgentMemory(mock_redis_manager)
        episodes = await memory.get_episodes("unknown-agent")
        assert episodes == []

    @pytest.mark.asyncio
    async def test_get_episodes_different_agents(self, mock_redis_manager: Any) -> None:
        """Episodes are namespaced per agent."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-a", {"event": "a-event"})
        await memory.add_episode("agent-b", {"event": "b-event"})

        episodes_a = await memory.get_episodes("agent-a")
        episodes_b = await memory.get_episodes("agent-b")
        assert len(episodes_a) == 1
        assert len(episodes_b) == 1
        assert episodes_a[0]["event"] == "a-event"
        assert episodes_b[0]["event"] == "b-event"

    @pytest.mark.asyncio
    async def test_search_episodes_found(self, mock_redis_manager: Any) -> None:
        """Search finds matching episodes."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-1", {"event": "signal", "direction": "BUY"})
        await memory.add_episode("agent-1", {"event": "signal", "direction": "SELL"})
        await memory.add_episode("agent-1", {"event": "error", "msg": "fail"})

        matches = await memory.search_episodes("agent-1", "BUY", limit=10)
        assert len(matches) == 1
        assert matches[0]["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_search_episodes_not_found(self, mock_redis_manager: Any) -> None:
        """Search returns empty when no match."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-1", {"event": "test"})

        matches = await memory.search_episodes("agent-1", "NONEXISTENT")
        assert matches == []

    @pytest.mark.asyncio
    async def test_search_episodes_limit(self, mock_redis_manager: Any) -> None:
        """Search respects limit."""
        memory = AgentMemory(mock_redis_manager)
        for i in range(10):
            await memory.add_episode("agent-1", {"event": "signal", "id": i})

        matches = await memory.search_episodes("agent-1", "signal", limit=3)
        assert len(matches) == 3

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, mock_redis_manager: Any) -> None:
        """Search is case-insensitive."""
        memory = AgentMemory(mock_redis_manager)
        await memory.add_episode("agent-1", {"event": "BUY_SIGNAL"})

        matches = await memory.search_episodes("agent-1", "buy")
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_add_episode_returns_false_on_error(self, mock_redis_manager: Any) -> None:
        """Returns False when Redis raises."""
        mock_redis_manager.client.lpush = None  # type: ignore[assignment]
        memory = AgentMemory(mock_redis_manager)
        # Should not raise — returns False
        result = await memory.add_episode("agent-1", {"event": "test"})
        assert result is False


# ---------------------------------------------------------------------------
# Semantic memory
# ---------------------------------------------------------------------------


class TestSemanticMemory:
    """Tests for semantic memory (store_knowledge, retrieve_knowledge)."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, mock_redis_manager: Any) -> None:
        """Store knowledge and retrieve it."""
        memory = AgentMemory(mock_redis_manager)
        result = await memory.store_knowledge("market_regime", "bullish")
        assert result is True

        value = await memory.retrieve_knowledge("market_regime")
        assert value == "bullish"

    @pytest.mark.asyncio
    async def test_store_dict(self, mock_redis_manager: Any) -> None:
        """Store a dict as knowledge."""
        memory = AgentMemory(mock_redis_manager)
        data = {"trend": "up", "strength": 0.8}
        await memory.store_knowledge("analysis", data)

        retrieved = await memory.retrieve_knowledge("analysis")
        assert retrieved == data

    @pytest.mark.asyncio
    async def test_retrieve_missing(self, mock_redis_manager: Any) -> None:
        """Retrieve returns None for missing key."""
        memory = AgentMemory(mock_redis_manager)
        value = await memory.retrieve_knowledge("nonexistent")
        assert value is None

    @pytest.mark.asyncio
    async def test_store_overwrite(self, mock_redis_manager: Any) -> None:
        """Store overwrites existing key."""
        memory = AgentMemory(mock_redis_manager)
        await memory.store_knowledge("key", "old")
        await memory.store_knowledge("key", "new")

        value = await memory.retrieve_knowledge("key")
        assert value == "new"

    @pytest.mark.asyncio
    async def test_store_returns_false_on_error(self, mock_redis_manager: Any) -> None:
        """Returns False when set fails."""
        async def fail_set(*args: Any, **kwargs: Any) -> bool:
            return False
        mock_redis_manager.set = fail_set
        memory = AgentMemory(mock_redis_manager)
        result = await memory.store_knowledge("key", "value")
        assert result is False


# ---------------------------------------------------------------------------
# Working memory
# ---------------------------------------------------------------------------


class TestWorkingMemory:
    """Tests for working memory (set_context, get_context)."""

    @pytest.mark.asyncio
    async def test_set_and_get_context(self, mock_redis_manager: Any) -> None:
        """Set and retrieve working context."""
        memory = AgentMemory(mock_redis_manager)
        result = await memory.set_context("agent-1", {"task": "scanning", "symbol": "SOL/USDC"})
        assert result is True

        ctx = await memory.get_context("agent-1")
        assert ctx is not None
        assert ctx["task"] == "scanning"
        assert ctx["symbol"] == "SOL/USDC"
        assert "_updated_at" in ctx

    @pytest.mark.asyncio
    async def test_get_context_missing(self, mock_redis_manager: Any) -> None:
        """Returns None for missing context."""
        memory = AgentMemory(mock_redis_manager)
        ctx = await memory.get_context("unknown-agent")
        assert ctx is None

    @pytest.mark.asyncio
    async def test_context_isolated_per_agent(self, mock_redis_manager: Any) -> None:
        """Contexts are namespaced per agent."""
        memory = AgentMemory(mock_redis_manager)
        await memory.set_context("agent-a", {"task": "a-task"})
        await memory.set_context("agent-b", {"task": "b-task"})

        ctx_a = await memory.get_context("agent-a")
        ctx_b = await memory.get_context("agent-b")
        assert ctx_a["task"] == "a-task"
        assert ctx_b["task"] == "b-task"

    @pytest.mark.asyncio
    async def test_set_context_returns_false_on_error(self, mock_redis_manager: Any) -> None:
        """Returns False when set fails."""
        async def fail_set(*args: Any, **kwargs: Any) -> bool:
            return False
        mock_redis_manager.set = fail_set
        memory = AgentMemory(mock_redis_manager)
        result = await memory.set_context("agent-1", {"task": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_get_context_returns_none_on_error(self, mock_redis_manager: Any) -> None:
        """Returns None when get raises."""
        async def fail_get(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("boom")
        mock_redis_manager.get = fail_get
        memory = AgentMemory(mock_redis_manager)
        ctx = await memory.get_context("agent-1")
        assert ctx is None


# ---------------------------------------------------------------------------
# Shared / inter-agent communication
# ---------------------------------------------------------------------------


class TestSharedMemory:
    """Tests for shared memory (publish_message, get_messages)."""

    @pytest.mark.asyncio
    async def test_publish_and_get(self, mock_redis_manager: Any) -> None:
        """Publish a message and retrieve it."""
        memory = AgentMemory(mock_redis_manager)
        length = await memory.publish_message("signals", {"type": "BUY", "symbol": "SOL/USDC"})
        assert length == 1

        messages = await memory.get_messages("signals")
        assert len(messages) == 1
        assert messages[0]["type"] == "BUY"

    @pytest.mark.asyncio
    async def test_publish_multiple(self, mock_redis_manager: Any) -> None:
        """Publish multiple messages."""
        memory = AgentMemory(mock_redis_manager)
        for i in range(3):
            await memory.publish_message("alerts", {"id": i})

        messages = await memory.get_messages("alerts")
        assert len(messages) == 3
        # Newest first
        assert messages[0]["id"] == 2
        assert messages[2]["id"] == 0

    @pytest.mark.asyncio
    async def test_get_messages_limit(self, mock_redis_manager: Any) -> None:
        """Limit controls message count."""
        memory = AgentMemory(mock_redis_manager)
        for i in range(5):
            await memory.publish_message("ch", {"id": i})

        messages = await memory.get_messages("ch", limit=2)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, mock_redis_manager: Any) -> None:
        """Empty list for unknown channel."""
        memory = AgentMemory(mock_redis_manager)
        messages = await memory.get_messages("nonexistent")
        assert messages == []

    @pytest.mark.asyncio
    async def test_publish_includes_timestamp(self, mock_redis_manager: Any) -> None:
        """Published messages include timestamp."""
        memory = AgentMemory(mock_redis_manager)
        await memory.publish_message("ch", {"data": 1})

        messages = await memory.get_messages("ch")
        assert "_published_at" in messages[0]

    @pytest.mark.asyncio
    async def test_publish_returns_zero_on_error(self, mock_redis_manager: Any) -> None:
        """Returns 0 when publish fails."""
        mock_redis_manager.client.lpush = None  # type: ignore[assignment]
        memory = AgentMemory(mock_redis_manager)
        result = await memory.publish_message("ch", {"data": 1})
        assert result == 0

    @pytest.mark.asyncio
    async def test_channels_isolated(self, mock_redis_manager: Any) -> None:
        """Different channels are isolated."""
        memory = AgentMemory(mock_redis_manager)
        await memory.publish_message("ch-a", {"msg": "a"})
        await memory.publish_message("ch-b", {"msg": "b"})

        msgs_a = await memory.get_messages("ch-a")
        msgs_b = await memory.get_messages("ch-b")
        assert len(msgs_a) == 1
        assert len(msgs_b) == 1
        assert msgs_a[0]["msg"] == "a"
        assert msgs_b[0]["msg"] == "b"
