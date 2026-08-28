"""DATS — Orchestrator Agent.

Coordinates all agents, resolves conflicts, monitors health, and manages
the lifecycle of the multi-agent system.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import BaseAgent
from agents.schemas import (
    AgentDecision,
    AgentHealth,
    AgentState,
    DecisionType,
)
from infra.redis_client import RedisManager
from infra.kafka_client import KafkaProducer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REGISTRY_KEY: str = "agents:registry"
_HEALTH_CHECK_INTERVAL_SECONDS: int = 30
_MAX_CONSECUTIVE_ERRORS: int = 5

# Conflict resolution priority (lower = higher priority)
_PRIORITY: dict[str, int] = {
    "risk": 1,
    "execution": 2,
    "strategy": 3,
    "orchestrator": 0,
}


class OrchestratorAgent(BaseAgent):
    """Coordinates all agents, resolves conflicts, manages lifecycle.

    Usage::

        orch = OrchestratorAgent("orch-1", redis, kafka)
        await orch.start()

        # Register agents
        await orch.register(strategy_agent)
        await orch.register(risk_agent)
        await orch.register(execution_agent)

        # Run the main loop
        await orch.run()
    """

    def __init__(
        self,
        agent_id: str,
        redis_manager: RedisManager,
        kafka_producer: KafkaProducer,
        health_check_interval: int = _HEALTH_CHECK_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="orchestrator")
        self._agents: dict[str, BaseAgent] = {}
        self._health_check_interval: int = health_check_interval
        self._running: bool = False
        self._cycles: int = 0

    # -- Agent registry -------------------------------------------------------

    async def register(self, agent: BaseAgent) -> None:
        """Register an agent with the orchestrator.

        Args:
            agent: The agent to register.
        """
        self._agents[agent.agent_id] = agent

        # Store in Redis registry
        try:
            registry = await self._redis.get(_REGISTRY_KEY) or {}
            if not isinstance(registry, dict):
                registry = {}
            registry[agent.agent_id] = {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "orchestrator": self.agent_id,
            }
            await self._redis.set(_REGISTRY_KEY, registry, ttl=None)
        except Exception as exc:
            self._log.warning("Failed to update registry: %s", exc)

        self._log.info(
            "Agent registered: %s (type=%s, total=%d)",
            agent.agent_id,
            agent.agent_type,
            len(self._agents),
        )

    async def unregister(self, agent_id: str) -> None:
        """Unregister an agent.

        Args:
            agent_id: Agent ID to unregister.
        """
        if agent_id in self._agents:
            agent = self._agents[agent_id]
            # Stop the agent if it's running
            try:
                if agent.state not in (AgentState.SHUTDOWN, AgentState.ERROR):
                    await agent.stop()
            except Exception as exc:
                self._log.warning("Error stopping agent %s during unregister: %s", agent_id, exc)
            del self._agents[agent_id]

        # Update Redis registry
        try:
            registry = await self._redis.get(_REGISTRY_KEY) or {}
            if isinstance(registry, dict) and agent_id in registry:
                del registry[agent_id]
                await self._redis.set(_REGISTRY_KEY, registry, ttl=None)
        except Exception as exc:
            self._log.warning("Failed to update registry: %s", exc)

        self._log.info("Agent unregistered: %s (total=%d)", agent_id, len(self._agents))

    async def get_agent(self, agent_id: str) -> BaseAgent | None:
        """Get a registered agent by ID.

        Args:
            agent_id: Agent ID.

        Returns:
            The agent instance, or ``None`` if not found.
        """
        return self._agents.get(agent_id)

    async def list_agents(self) -> list[AgentHealth]:
        """List health status of all registered agents.

        Returns:
            List of ``AgentHealth`` objects.
        """
        health_list: list[AgentHealth] = []
        for agent in self._agents.values():
            try:
                health = await agent.health()
                health_list.append(health)
            except Exception as exc:
                self._log.warning("Failed to get health for %s: %s", agent.agent_id, exc)
                health_list.append(
                    AgentHealth(
                        agent_id=agent.agent_id,
                        state=AgentState.ERROR,
                        error_count=-1,
                        metadata={"error": str(exc)},
                    )
                )
        return health_list

    # -- Core loop overrides --------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Collect health, detect conflicts, resolve.

        Args:
            context: Current context.

        Returns:
            Coordination decision.
        """
        self._log.debug("Orchestrator %s thinking", self.agent_id)

        # Collect health from all agents
        health_list = await self.list_agents()

        # Detect failed agents
        failed_agents: list[str] = []
        for health in health_list:
            if health.state == AgentState.ERROR:
                failed_agents.append(health.agent_id)

        # Detect conflicts: check for opposing decisions in memory
        conflict_resolution = await self._detect_conflicts()

        payload: dict[str, Any] = {
            "agent_count": len(self._agents),
            "health": [h.model_dump(mode="json") for h in health_list],
            "failed_agents": failed_agents,
            "conflict_resolution": conflict_resolution,
        }

        if conflict_resolution:
            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.COORDINATION,
                payload=payload,
                reasoning=f"Conflicts detected and resolved: {conflict_resolution}",
            )

        if failed_agents:
            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.COORDINATION,
                payload=payload,
                reasoning=f"Failed agents detected: {failed_agents}",
            )

        return AgentDecision(
            agent_id=self.agent_id,
            decision_type=DecisionType.NOOP,
            payload=payload,
            reasoning="All agents healthy, no conflicts detected.",
        )

    async def act(self, decision: AgentDecision) -> None:
        """Dispatch commands: restart failed agents, apply resolutions.

        Args:
            decision: The coordination decision.
        """
        if decision.decision_type != DecisionType.COORDINATION:
            return

        # Restart failed agents
        failed = decision.payload.get("failed_agents", [])
        for agent_id in failed:
            await self._restart_agent(agent_id)

        # Apply conflict resolutions
        resolutions = decision.payload.get("conflict_resolution", [])
        for resolution in resolutions:
            action = resolution.get("action")
            target_agent = resolution.get("target_agent")
            if action and target_agent:
                await self._apply_resolution(action, target_agent, resolution)

        # Update orchestration state
        await self.remember(
            "orchestration:state",
            {
                "cycle": self._cycles,
                "agent_count": len(self._agents),
                "failed_agents": failed,
                "resolutions": resolutions,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            ttl=300,
        )

    # -- Main loop ------------------------------------------------------------

    async def run(self) -> None:
        """Run the main orchestration loop.

        Periodically checks health, resolves conflicts, manages agent lifecycle.
        Runs until ``stop()`` is called.
        """
        self._running = True
        self._log.info("Orchestrator %s main loop started", self.agent_id)

        while self._running:
            try:
                self._cycles += 1
                await self.run_cycle()

                # Check for agents that need restart
                for agent_id, agent in list(self._agents.items()):
                    if agent.state == AgentState.ERROR and agent._error_count < _MAX_CONSECUTIVE_ERRORS:
                        self._log.info("Auto-restarting agent %s", agent_id)
                        try:
                            agent.state = AgentState.INITIALIZING
                            await agent.start()
                        except Exception as exc:
                            self._log.error("Failed to restart agent %s: %s", agent_id, exc)

                await asyncio.sleep(self._health_check_interval)

            except asyncio.CancelledError:
                self._log.info("Orchestrator loop cancelled")
                break
            except Exception as exc:
                self._log.error("Orchestrator loop error: %s", exc)
                self._error_count += 1
                await asyncio.sleep(5)

        self._log.info("Orchestrator %s main loop exited", self.agent_id)

    async def stop(self) -> None:
        """Graceful shutdown of orchestrator and all registered agents."""
        self._log.info("Orchestrator %s stopping all agents", self.agent_id)
        self._running = False

        # Stop all agents in priority order (risk first, then execution, then strategy)
        sorted_agents = sorted(
            self._agents.values(),
            key=lambda a: _PRIORITY.get(a.agent_type, 99),
        )

        for agent in sorted_agents:
            try:
                self._log.debug("Stopping agent %s", agent.agent_id)
                await agent.stop()
            except Exception as exc:
                self._log.warning("Error stopping agent %s: %s", agent.agent_id, exc)

        self._agents.clear()
        await super().stop()

    # -- Conflict resolution --------------------------------------------------

    async def _detect_conflicts(self) -> list[dict[str, Any]]:
        """Detect and resolve conflicts between agents.

        Checks recent decisions from all agents.  Risk decisions always win.

        Returns:
            List of resolution dicts with ``action`` and ``target_agent``.
        """
        resolutions: list[dict[str, Any]] = []

        # Check for kill switch
        try:
            kill_flag = await self._redis.get("global:kill_switch")
            if isinstance(kill_flag, dict) and kill_flag.get("active"):
                # If kill switch is active, all strategy signals should be blocked
                for agent_id, agent in self._agents.items():
                    if agent.agent_type == "strategy":
                        resolutions.append({
                            "action": "block_signals",
                            "target_agent": agent_id,
                            "reason": "kill_switch_active",
                        })
                return resolutions
        except Exception as exc:
            self._log.debug("Error checking kill switch: %s", exc)

        # Check agent states for direct conflicts
        risk_agent_states = []
        strategy_agent_states = []

        for agent_id, agent in self._agents.items():
            if agent.agent_type == "risk":
                risk_agent_states.append((agent_id, agent.state))
            elif agent.agent_type == "strategy":
                strategy_agent_states.append((agent_id, agent.state))

        # If risk agent has issued critical alert, block all strategy actions
        for agent_id, state in risk_agent_states:
            if state == AgentState.ACTING:
                try:
                    latest = await agent.recall("latest_assessment")
                    if isinstance(latest, dict) and latest.get("risk_level") == "CRITICAL":
                        for sid, _ in strategy_agent_states:
                            resolutions.append({
                                "action": "block_signals",
                                "target_agent": sid,
                                "reason": f"risk_critical_from_{agent_id}",
                            })
                except Exception:
                    pass

        return resolutions

    async def _apply_resolution(
        self,
        action: str,
        target_agent_id: str,
        resolution: dict[str, Any],
    ) -> None:
        """Apply a conflict resolution.

        Args:
            action: Resolution action (e.g., "block_signals").
            target_agent_id: Target agent ID.
            resolution: Full resolution dict.
        """
        agent = self._agents.get(target_agent_id)
        if agent is None:
            return

        if action == "block_signals":
            self._log.info(
                "Blocking signals from %s (reason=%s)",
                target_agent_id,
                resolution.get("reason"),
            )
            try:
                await agent._memory.set_context(
                    target_agent_id,
                    {"signal_blocked": True, "reason": resolution.get("reason")},
                )
            except Exception as exc:
                self._log.warning("Failed to block signals for %s: %s", target_agent_id, exc)

    async def _restart_agent(self, agent_id: str) -> None:
        """Restart a failed agent.

        Args:
            agent_id: Agent ID to restart.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            return

        self._log.info("Restarting agent %s", agent_id)
        try:
            if agent.state not in (AgentState.SHUTDOWN,):
                try:
                    await agent.stop()
                except Exception:
                    pass
            agent._error_count = 0
            agent.state = AgentState.INITIALIZING
            await agent.start()
            self._log.info("Agent %s restarted successfully", agent_id)
        except Exception as exc:
            self._log.error("Failed to restart agent %s: %s", agent_id, exc)

    # -- Health monitoring ----------------------------------------------------

    async def get_registry(self) -> dict[str, Any]:
        """Get the agent registry from Redis.

        Returns:
            Registry dict mapping agent_id → metadata.
        """
        try:
            registry = await self._redis.get(_REGISTRY_KEY)
            if isinstance(registry, dict):
                return registry
        except Exception as exc:
            self._log.warning("Failed to read registry: %s", exc)
        return {}
