"""DATS — Agent Memory (Episodic + Semantic + Working).

Provides three-tier memory backed by Redis:
* **Episodic** — time-ordered events with TTL (auto-expiring).
* **Semantic**   — long-term key-value knowledge store.
* **Working**    — current task context (short-lived).
* **Shared**     — inter-agent communication via Redis lists.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_EPISODE_TTL: int = 86400  # 24 hours
_DEFAULT_CONTEXT_TTL: int = 300    # 5 minutes
_REDIS_NS_EPISODES: str = "memory:{agent_id}:episodes"
_REDIS_NS_CONTEXT: str = "memory:{agent_id}:context"
_REDIS_NS_KNOWLEDGE: str = "memory:knowledge"
_REDIS_NS_SHARED: str = "memory:shared:{channel}"


class AgentMemory:
    """Three-tier agent memory backed by Redis.

    Usage::

        memory = AgentMemory(redis_manager)

        # Episodic — record events
        await memory.add_episode("agent-1", {"event": "signal", "direction": "BUY"})
        episodes = await memory.get_episodes("agent-1", limit=10)

        # Semantic — store knowledge
        await memory.store_knowledge("market_regime", "bullish")
        regime = await memory.retrieve_knowledge("market_regime")

        # Working — current context
        await memory.set_context("agent-1", {"task": "scanning", "symbol": "SOL/USDC"})
        ctx = await memory.get_context("agent-1")
    """

    def __init__(self, redis_manager: Any) -> None:
        self._redis = redis_manager

    # -- Episodic memory ------------------------------------------------------

    async def add_episode(
        self,
        agent_id: str,
        episode: dict[str, Any],
        ttl: int = _DEFAULT_EPISODE_TTL,
    ) -> bool:
        """Add an episodic event to the agent's memory.

        Stores as a JSON object with auto-generated timestamp at the
        Redis list head (LPUSH) so ``get_episodes`` returns newest first.

        Args:
            agent_id: Agent identifier.
            episode: Event dict to store.
            ttl: Time-to-live for the entire episode list in seconds.

        Returns:
            ``True`` if the episode was added successfully.
        """
        key = _REDIS_NS_EPISODES.format(agent_id=agent_id)
        enriched = dict(episode)
        enriched["_stored_at"] = datetime.now(timezone.utc).isoformat()
        enriched["_agent_id"] = agent_id

        try:
            # LPUSH stores newest at index 0
            await self._redis.client.lpush(key, json.dumps(enriched, default=str))
            # Refresh TTL on every write
            await self._redis.client.expire(key, ttl)
            logger.debug("Episode added for %s: %s", agent_id, episode)
            return True
        except Exception as exc:
            logger.error("Failed to add episode for %s: %s", agent_id, exc)
            return False

    async def get_episodes(
        self,
        agent_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve recent episodic events for an agent.

        Returns newest-first (most recent episode at index 0).

        Args:
            agent_id: Agent identifier.
            limit: Maximum number of episodes to return.

        Returns:
            List of episode dicts.
        """
        key = _REDIS_NS_EPISODES.format(agent_id=agent_id)
        try:
            raw_items = await self._redis.client.lrange(key, 0, limit - 1)
            episodes: list[dict[str, Any]] = []
            for raw in raw_items:
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(parsed, dict):
                        episodes.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Unparseable episode for %s: %r", agent_id, raw)
            return episodes
        except Exception as exc:
            logger.error("Failed to get episodes for %s: %s", agent_id, exc)
            return []

    async def search_episodes(
        self,
        agent_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search episodes for a keyword (simple substring match).

        Args:
            agent_id: Agent identifier.
            query: Substring to search for.
            limit: Maximum matches to return.

        Returns:
            Matching episode dicts.
        """
        episodes = await self.get_episodes(agent_id, limit=limit * 5)
        query_lower = query.lower()
        matches: list[dict[str, Any]] = []
        for ep in episodes:
            # Flatten dict values to strings for searching
            flat = json.dumps(ep, default=str).lower()
            if query_lower in flat:
                matches.append(ep)
                if len(matches) >= limit:
                    break
        return matches

    # -- Semantic memory ------------------------------------------------------

    async def store_knowledge(self, key: str, value: Any) -> bool:
        """Store long-term knowledge (no TTL — persistent).

        Args:
            key: Knowledge key.
            value: Any JSON-serialisable value.

        Returns:
            ``True`` on success.
        """
        redis_key = f"{_REDIS_NS_KNOWLEDGE}:{key}"
        try:
            return await self._redis.set(redis_key, value, ttl=None)
        except Exception as exc:
            logger.error("Failed to store knowledge %s: %s", key, exc)
            return False

    async def retrieve_knowledge(self, key: str) -> Any | None:
        """Retrieve long-term knowledge.

        Args:
            key: Knowledge key.

        Returns:
            The stored value, or ``None`` if not found.
        """
        redis_key = f"{_REDIS_NS_KNOWLEDGE}:{key}"
        try:
            return await self._redis.get(redis_key)
        except Exception as exc:
            logger.error("Failed to retrieve knowledge %s: %s", key, exc)
            return None

    # -- Working memory -------------------------------------------------------

    async def set_context(
        self,
        agent_id: str,
        context: dict[str, Any],
        ttl: int = _DEFAULT_CONTEXT_TTL,
    ) -> bool:
        """Set the current working context for an agent.

        Args:
            agent_id: Agent identifier.
            context: Context dict.
            ttl: Time-to-live in seconds.

        Returns:
            ``True`` on success.
        """
        key = _REDIS_NS_CONTEXT.format(agent_id=agent_id)
        enriched = dict(context)
        enriched["_updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            return await self._redis.set(key, enriched, ttl=ttl)
        except Exception as exc:
            logger.error("Failed to set context for %s: %s", agent_id, exc)
            return False

    async def get_context(self, agent_id: str) -> dict[str, Any] | None:
        """Get the current working context for an agent.

        Args:
            agent_id: Agent identifier.

        Returns:
            Context dict, or ``None`` if not found / expired.
        """
        key = _REDIS_NS_CONTEXT.format(agent_id=agent_id)
        try:
            result = await self._redis.get(key)
            if isinstance(result, dict):
                return result
            return None
        except Exception as exc:
            logger.error("Failed to get context for %s: %s", agent_id, exc)
            return None

    # -- Shared / inter-agent communication -----------------------------------

    async def publish_message(self, channel: str, message: dict[str, Any]) -> int:
        """Publish a message to a shared channel (Redis LPUSH).

        Args:
            channel: Channel name.
            message: Message dict.

        Returns:
            New length of the list, or 0 on failure.
        """
        key = _REDIS_NS_SHARED.format(channel=channel)
        enriched = dict(message)
        enriched["_published_at"] = datetime.now(timezone.utc).isoformat()
        try:
            return await self._redis.client.lpush(key, json.dumps(enriched, default=str))
        except Exception as exc:
            logger.error("Failed to publish message to %s: %s", channel, exc)
            return 0

    async def get_messages(
        self,
        channel: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve messages from a shared channel.

        Args:
            channel: Channel name.
            limit: Maximum messages to retrieve.

        Returns:
            List of message dicts, newest first.
        """
        key = _REDIS_NS_SHARED.format(channel=channel)
        try:
            raw_items = await self._redis.client.lrange(key, 0, limit - 1)
            messages: list[dict[str, Any]] = []
            for raw in raw_items:
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(parsed, dict):
                        messages.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Unparseable message in %s: %r", channel, raw)
            return messages
        except Exception as exc:
            logger.error("Failed to get messages from %s: %s", channel, exc)
            return []
