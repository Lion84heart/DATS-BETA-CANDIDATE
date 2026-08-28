"""Tests for OrchestratorAgent: registry, conflict resolution, health."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.base import BaseAgent
from src.agents.execution import ExecutionAgent
from src.agents.orchestrator import OrchestratorAgent
from src.agents.risk import RiskAgent
from src.agents.schemas import AgentDecision, AgentState, DecisionType
from src.agents.strategy import StrategyAgent


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for OrchestratorAgent construction."""

    def test_default_params(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Default parameters."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        assert orch.agent_type == "orchestrator"
        assert orch._health_check_interval > 0
        assert len(orch._agents) == 0

    def test_custom_interval(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Custom health check interval."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer, health_check_interval=10)
        assert orch._health_check_interval == 10


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for OrchestratorAgent lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Orchestrator starts correctly."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        assert orch.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Orchestrator stops correctly."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.stop()
        assert orch.state == AgentState.SHUTDOWN
        assert orch._running is False

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Works as async context manager."""
        async with OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer) as orch:
            assert orch.state == AgentState.IDLE


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------


class TestRegistry:
    """Tests for agent registration."""

    @pytest.mark.asyncio
    async def test_register_agent(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Register an agent."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await orch.register(agent)
        assert "strat-1" in orch._agents
        assert len(orch._agents) == 1

    @pytest.mark.asyncio
    async def test_unregister_agent(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Unregister an agent."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await orch.register(agent)
        await orch.unregister("strat-1")
        assert "strat-1" not in orch._agents
        assert len(orch._agents) == 0

    @pytest.mark.asyncio
    async def test_get_agent(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Get agent by ID."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await orch.register(agent)
        retrieved = await orch.get_agent("strat-1")
        assert retrieved is not None
        assert retrieved.agent_id == "strat-1"

    @pytest.mark.asyncio
    async def test_get_agent_missing(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Get missing agent returns None."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        retrieved = await orch.get_agent("nonexistent")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_register_multiple(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Register multiple agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        await orch.register(RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer))
        await orch.register(ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer))
        assert len(orch._agents) == 3

    @pytest.mark.asyncio
    async def test_register_stores_in_redis(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Registration stores metadata in Redis."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await orch.register(agent)
        registry = await mock_redis_manager.get("agents:registry")
        assert registry is not None
        if isinstance(registry, dict):
            assert "strat-1" in registry


# ---------------------------------------------------------------------------
# Health monitoring
# ---------------------------------------------------------------------------


class TestHealthMonitoring:
    """Tests for health monitoring."""

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """List agents when empty."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        health_list = await orch.list_agents()
        assert health_list == []

    @pytest.mark.asyncio
    async def test_list_agents(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """List health of all registered agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        await orch.register(agent)
        health_list = await orch.list_agents()
        assert len(health_list) == 1
        assert health_list[0].agent_id == "strat-1"

    @pytest.mark.asyncio
    async def test_list_agents_with_error_state(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """List agents includes error state."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        agent.state = AgentState.ERROR
        agent._error_count = 5
        await orch.register(agent)
        health_list = await orch.list_agents()
        assert health_list[0].state == AgentState.ERROR
        assert health_list[0].error_count == 5


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


class TestConflictResolution:
    """Tests for conflict detection and resolution."""

    @pytest.mark.asyncio
    async def test_no_conflicts(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """No conflicts with healthy agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        decision = await orch.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_kill_switch_conflict(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Kill switch blocks strategy signals."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        # Set kill switch
        await mock_redis_manager.set("global:kill_switch", {"active": True})
        decision = await orch.think({})
        assert decision.decision_type == DecisionType.COORDINATION
        resolutions = decision.payload.get("conflict_resolution", [])
        assert any(r["action"] == "block_signals" for r in resolutions)

    @pytest.mark.asyncio
    async def test_detect_conflicts_kill_switch(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """_detect_conflicts finds kill switch."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        await mock_redis_manager.set("global:kill_switch", {"active": True})
        resolutions = await orch._detect_conflicts()
        assert len(resolutions) > 0
        assert resolutions[0]["action"] == "block_signals"

    @pytest.mark.asyncio
    async def test_no_kill_switch_no_conflicts(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """No conflicts when kill switch is inactive."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        resolutions = await orch._detect_conflicts()
        assert resolutions == []

    @pytest.mark.asyncio
    async def test_apply_resolution(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Apply block_signals resolution."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        await orch.register(agent)
        await orch._apply_resolution("block_signals", "strat-1", {"reason": "test"})
        ctx = await agent._memory.get_context("strat-1")
        assert ctx is not None
        assert ctx.get("signal_blocked") is True


# ---------------------------------------------------------------------------
# Think / Act
# ---------------------------------------------------------------------------


class TestThinkAct:
    """Tests for think() and act()."""

    @pytest.mark.asyncio
    async def test_think_no_agents(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """think() with no agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        decision = await orch.think({})
        assert decision.decision_type == DecisionType.NOOP
        assert decision.payload["agent_count"] == 0

    @pytest.mark.asyncio
    async def test_think_with_agents(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """think() with registered agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        await orch.register(RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer))
        decision = await orch.think({})
        assert decision.payload["agent_count"] == 2

    @pytest.mark.asyncio
    async def test_act_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """act() with NOOP does nothing."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        decision = AgentDecision(
            agent_id="orch-1",
            decision_type=DecisionType.NOOP,
            payload={"failed_agents": [], "conflict_resolution": []},
        )
        await orch.act(decision)
        # Should not raise

    @pytest.mark.asyncio
    async def test_act_restarts_failed(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """act() restarts failed agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        agent.state = AgentState.ERROR
        await orch.register(agent)
        decision = AgentDecision(
            agent_id="orch-1",
            decision_type=DecisionType.COORDINATION,
            payload={"failed_agents": ["strat-1"], "conflict_resolution": []},
        )
        await orch.act(decision)


# ---------------------------------------------------------------------------
# Agent restart
# ---------------------------------------------------------------------------


class TestAgentRestart:
    """Tests for agent restart functionality."""

    @pytest.mark.asyncio
    async def test_restart_agent(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Restart a failed agent."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        agent = StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store)
        await agent.start()
        agent.state = AgentState.ERROR
        await orch.register(agent)
        await orch._restart_agent("strat-1")
        # Agent should be back to IDLE
        assert orch._agents["strat-1"].state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_restart_missing_agent(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Restart missing agent does nothing."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch._restart_agent("nonexistent")  # Should not raise


# ---------------------------------------------------------------------------
# Registry from Redis
# ---------------------------------------------------------------------------


class TestRegistryRedis:
    """Tests for Redis-backed registry."""

    @pytest.mark.asyncio
    async def test_get_registry_empty(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Get empty registry."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        registry = await orch.get_registry()
        assert registry == {}

    @pytest.mark.asyncio
    async def test_get_registry_with_data(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Get registry with data."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await mock_redis_manager.set("agents:registry", {"agent-1": {"type": "test"}})
        registry = await orch.get_registry()
        assert "agent-1" in registry


# ---------------------------------------------------------------------------
# Full cycle
# ---------------------------------------------------------------------------


class TestFullCycle:
    """Tests for run_cycle with OrchestratorAgent."""

    @pytest.mark.asyncio
    async def test_run_cycle(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """Full cycle."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        await orch.run_cycle()
        assert orch.state == AgentState.IDLE
        assert orch._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_health(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health report."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        health = await orch.health()
        assert health.agent_id == "orch-1"
        assert health.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop_clears_agents(self, mock_redis_manager: Any, mock_kafka_producer: Any, mock_feature_store: Any) -> None:
        """stop() clears all agents."""
        orch = OrchestratorAgent("orch-1", mock_redis_manager, mock_kafka_producer)
        await orch.start()
        await orch.register(StrategyAgent("strat-1", mock_redis_manager, mock_kafka_producer, mock_feature_store))
        await orch.register(RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer))
        assert len(orch._agents) == 2
        await orch.stop()
        assert len(orch._agents) == 0
