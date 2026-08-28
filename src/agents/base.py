"""DATS — Abstract Base Agent.

Provides the lifecycle, communication, and memory primitives that all
DATS agents inherit.  Uses Redis for state + memory and Kafka for
inter-agent messaging.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from agents.memory import AgentMemory
from agents.schemas import AgentDecision, AgentHealth, AgentMessage, AgentState
from infra.config import get_config
from infra.kafka_client import KafkaProducer, TRADING_SIGNALS
from infra.redis_client import RedisManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class AgentError(Exception):
    """Base exception for agent-related errors."""


class AgentNotStartedError(AgentError):
    """Raised when an operation is called before start()."""


class AgentStateError(AgentError):
    """Raised on invalid state transitions."""


# ---------------------------------------------------------------------------
# BaseAgent
# ---------------------------------------------------------------------------


class BaseAgent(ABC):
    """Abstract base for all DATS agents.

    Lifecycle::

        agent = MyAgent("my-agent", redis_manager, kafka_producer)
        await agent.start()   # → INITIALIZING → IDLE
        await agent.run_cycle()  # → THINKING → ACTING → IDLE
        await agent.stop()    # → SHUTDOWN

    All agents support async context-manager usage::

        async with MyAgent(...) as agent:
            await agent.run_cycle()
    """

    def __init__(
        self,
        agent_id: str,
        redis_manager: RedisManager,
        kafka_producer: KafkaProducer,
        agent_type: str = "base",
    ) -> None:
        self.agent_id: str = agent_id
        self.agent_type: str = agent_type
        self.state: AgentState = AgentState.INITIALIZING
        self._redis: RedisManager = redis_manager
        self._kafka: KafkaProducer = kafka_producer
        self._memory: AgentMemory = AgentMemory(redis_manager)
        self._error_count: int = 0
        self._tasks_completed: int = 0
        self._started: bool = False
        self._log = logging.getLogger(f"{__name__}.{agent_id}")
        self._last_active: datetime = datetime.now(timezone.utc)
        self._settings = get_config()

    # -- Context manager ------------------------------------------------------

    async def __aenter__(self) -> BaseAgent:
        await self.start()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.stop()

    # -- Lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        """Initialise the agent and transition to IDLE.

        Idempotent — safe to call multiple times.
        """
        if self._started:
            self._log.debug("Agent already started.")
            return

        self._log.info("Starting agent %s (type=%s)", self.agent_id, self.agent_type)
        self.state = AgentState.INITIALIZING

        try:
            # Store agent registration in Redis
            await self.remember(
                "metadata",
                {
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "state": self.state.value,
                },
            )
            self.state = AgentState.IDLE
            self._started = True
            self._last_active = datetime.now(timezone.utc)
            self._log.info("Agent %s started → %s", self.agent_id, self.state.value)
        except Exception as exc:
            self.state = AgentState.ERROR
            self._error_count += 1
            self._log.error("Agent %s failed to start: %s", self.agent_id, exc)
            raise AgentError(f"Failed to start agent {self.agent_id}: {exc}") from exc

    async def stop(self) -> None:
        """Graceful shutdown. Transition to SHUTDOWN.

        Idempotent — safe to call multiple times.
        """
        self._log.info("Stopping agent %s", self.agent_id)
        self.state = AgentState.SHUTDOWN
        self._started = False
        self._last_active = datetime.now(timezone.utc)

        # Update state in Redis
        try:
            await self.remember(
                "metadata",
                {
                    "agent_id": self.agent_id,
                    "agent_type": self.agent_type,
                    "stopped_at": datetime.now(timezone.utc).isoformat(),
                    "state": self.state.value,
                },
            )
        except Exception as exc:
            self._log.warning("Failed to update shutdown state in Redis: %s", exc)

        self._log.info("Agent %s stopped → %s", self.agent_id, self.state.value)

    async def health(self) -> AgentHealth:
        """Return the current health status of the agent."""
        metadata: dict[str, Any] = {}
        try:
            raw = await self.recall(f"agent:{self.agent_id}:metadata")
            if isinstance(raw, dict):
                metadata = raw
        except Exception as exc:
            self._log.debug("Could not read metadata for health: %s", exc)

        return AgentHealth(
            agent_id=self.agent_id,
            state=self.state,
            last_active=self._last_active,
            error_count=self._error_count,
            tasks_completed=self._tasks_completed,
            metadata={
                "agent_type": self.agent_type,
                "started": self._started,
                **metadata,
            },
        )

    # -- Core loop ------------------------------------------------------------

    async def run_cycle(self) -> None:
        """Execute one full THINK → ACT cycle.

        Catches exceptions, transitions to ERROR state, and logs.
        The caller is responsible for recovery / restart.
        """
        if self.state == AgentState.SHUTDOWN:
            self._log.warning("Agent %s is shutdown — skipping cycle", self.agent_id)
            return

        if not self._started:
            raise AgentNotStartedError(f"Agent {self.agent_id} not started — call start() first.")

        context = await self._build_context()

        try:
            # THINK
            self.state = AgentState.THINKING
            self._last_active = datetime.now(timezone.utc)
            self._log.debug("Agent %s → THINKING", self.agent_id)
            decision = await self.think(context)

            # ACT
            self.state = AgentState.ACTING
            self._last_active = datetime.now(timezone.utc)
            self._log.debug("Agent %s → ACTING (decision=%s)", self.agent_id, decision.decision_type)
            await self.act(decision)

            self._tasks_completed += 1
            self.state = AgentState.IDLE
            self._last_active = datetime.now(timezone.utc)
            self._log.debug("Agent %s → IDLE", self.agent_id)

        except Exception as exc:
            self.state = AgentState.ERROR
            self._error_count += 1
            self._last_active = datetime.now(timezone.utc)
            self._log.error(
                "Agent %s cycle error (error_count=%d): %s",
                self.agent_id,
                self._error_count,
                exc,
                exc_info=True,
            )
            # Store error in memory for debugging
            try:
                await self._memory.add_episode(
                    self.agent_id,
                    {
                        "event": "error",
                        "error": str(exc),
                        "state": self.state.value,
                    },
                )
            except Exception:
                pass  # Best-effort

    @abstractmethod
    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Reasoning phase — OVERRIDE in subclasses.

        Args:
            context: Current context dict built by ``_build_context``.

        Returns:
            An ``AgentDecision`` describing what action to take.
        """
        ...

    @abstractmethod
    async def act(self, decision: AgentDecision) -> None:
        """Action phase — OVERRIDE in subclasses.

        Args:
            decision: The decision produced by ``think()``.
        """
        ...

    # -- Communication --------------------------------------------------------

    async def send_message(
        self,
        to_agent: str,
        msg_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Send a message to another agent via Kafka.

        Args:
            to_agent: Target agent ID.
            msg_type: Message type string.
            payload: Message payload dict.
        """
        message = AgentMessage(
            from_agent=self.agent_id,
            to_agent=to_agent,
            message_type=msg_type,
            payload=payload,
        )
        try:
            await self._kafka.send(
                TRADING_SIGNALS,
                value=message.model_dump(mode="json"),
                key=f"{self.agent_id}->{to_agent}",
            )
            self._log.debug(
                "Message sent %s → %s (type=%s)",
                self.agent_id,
                to_agent,
                msg_type,
            )
        except Exception as exc:
            self._log.error(
                "Failed to send message %s → %s: %s",
                self.agent_id,
                to_agent,
                exc,
            )

    async def receive_messages(
        self,
    ) -> AsyncGenerator[AgentMessage, None]:
        """Yield messages addressed to this agent.

        This is a stub that reads from Redis shared memory.
        In production, a dedicated Kafka consumer would be used.

        Yields:
            ``AgentMessage`` instances.
        """
        # Read from shared memory channel for this agent
        channel = f"agent:{self.agent_id}:inbox"
        messages = await self._memory.get_messages(channel, limit=50)
        for msg in messages:
            try:
                # Only yield messages addressed to this agent
                to_agent = msg.get("to_agent")
                if to_agent is None or to_agent == self.agent_id:
                    yield AgentMessage(
                        from_agent=msg.get("from_agent", "unknown"),
                        to_agent=to_agent,
                        message_type=msg.get("message_type", "unknown"),
                        payload=msg.get("payload", {}),
                    )
            except Exception as exc:
                self._log.warning("Failed to parse message: %s", exc)

    # -- Memory (Redis-backed) ------------------------------------------------

    async def remember(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Store a value in Redis memory.

        Args:
            key: Redis key (will be prefixed with ``agent:{agent_id}:``).
            value: JSON-serialisable value.
            ttl: Time-to-live in seconds.

        Returns:
            ``True`` on success.
        """
        full_key = f"agent:{self.agent_id}:{key}"
        try:
            return await self._redis.set(full_key, value, ttl=ttl)
        except Exception as exc:
            self._log.error("Failed to remember %s: %s", full_key, exc)
            return False

    async def recall(self, key: str) -> Any | None:
        """Retrieve a value from Redis memory.

        Args:
            key: Redis key (will be prefixed).

        Returns:
            The stored value, or ``None``.
        """
        full_key = f"agent:{self.agent_id}:{key}"
        try:
            return await self._redis.get(full_key)
        except Exception as exc:
            self._log.error("Failed to recall %s: %s", full_key, exc)
            return None

    async def forget(self, key: str) -> int:
        """Delete a value from Redis memory.

        Args:
            key: Redis key (will be prefixed).

        Returns:
            Number of keys deleted.
        """
        full_key = f"agent:{self.agent_id}:{key}"
        try:
            return await self._redis.delete(full_key)
        except Exception as exc:
            self._log.error("Failed to forget %s: %s", full_key, exc)
            return 0

    # -- Internal helpers -----------------------------------------------------

    async def _build_context(self) -> dict[str, Any]:
        """Build the context dict for the THINK phase.

        Returns:
            Dict with agent metadata, recent episodes, and working context.
        """
        episodes = await self._memory.get_episodes(self.agent_id, limit=10)
        working_ctx = await self._memory.get_context(self.agent_id)
        return {
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "state": self.state.value,
            "error_count": self._error_count,
            "tasks_completed": self._tasks_completed,
            "recent_episodes": episodes,
            "working_context": working_ctx or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
