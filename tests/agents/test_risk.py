"""Tests for RiskAgent: limit checks, VaR, kill switch."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.risk import RiskAgent
from src.agents.schemas import AgentDecision, AgentState, DecisionType, RiskAssessment


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for RiskAgent construction."""

    def test_default_params(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Default risk parameters."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        assert agent.agent_type == "risk"
        assert agent.max_position_size > 0
        assert agent.max_drawdown > 0
        assert agent.var_limit > 0
        assert agent.exposure_limit > 0

    def test_custom_params(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Custom risk parameters."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_position_size=0.2,
            max_drawdown=0.1,
            var_limit=0.05,
            exposure_limit=0.3,
        )
        assert agent.max_position_size == 0.2
        assert agent.max_drawdown == 0.1
        assert agent.var_limit == 0.05
        assert agent.exposure_limit == 0.3

    def test_default_kelly_fraction(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Default Kelly fraction."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        assert agent.kelly_fraction == 0.25


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for RiskAgent lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """RiskAgent starts correctly."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """RiskAgent stops correctly."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Works as async context manager."""
        async with RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer) as agent:
            assert agent.state == AgentState.IDLE


# ---------------------------------------------------------------------------
# Think / risk assessment
# ---------------------------------------------------------------------------


class TestThink:
    """Tests for think() method."""

    @pytest.mark.asyncio
    async def test_all_clear_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """All metrics within limits → NOOP."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            var_limit=1.0,  # Very high so VaR doesn't trigger
        )
        await agent.start()
        context = {
            "portfolio_value": 10000.0,
            "exposure_by_asset": {"SOL/USDC": 500.0},
            "peak_value": 10000.0,
        }
        decision = await agent.think(context)
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_position_size_breach(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Position size breach → RISK_ALERT."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_position_size=0.01,  # Very low limit
            exposure_limit=1.0,  # Very high so total exposure doesn't trigger
            var_limit=1.0,  # Very high so VaR doesn't trigger
        )
        await agent.start()
        context = {
            "portfolio_value": 10000.0,
            "exposure_by_asset": {"SOL/USDC": 5000.0},  # 50% — way over limit
            "peak_value": 10000.0,
        }
        decision = await agent.think(context)
        assert decision.decision_type == DecisionType.RISK_ALERT
        assessment = decision.payload.get("assessment", {})
        assert any("position_size" in b for b in assessment.get("breached_limits", []))

    @pytest.mark.asyncio
    async def test_drawdown_breach(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Drawdown breach → RISK_ALERT."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_drawdown=0.01,  # Very low limit
            var_limit=1.0,  # Very high so VaR doesn't trigger
        )
        await agent.start()
        context = {
            "portfolio_value": 9800.0,
            "exposure_by_asset": {},
            "peak_value": 10000.0,  # 2% drawdown — breaches but not critical
        }
        decision = await agent.think(context)
        assert decision.decision_type == DecisionType.RISK_ALERT
        assessment = decision.payload.get("assessment", {})
        assert any("drawdown" in b for b in assessment.get("breached_limits", []))

    @pytest.mark.asyncio
    async def test_critical_drawdown_kill_switch(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Critical drawdown → KILL_SWITCH."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_drawdown=0.05,
        )
        await agent.start()
        context = {
            "portfolio_value": 8000.0,
            "exposure_by_asset": {"SOL/USDC": 6000.0},
            "peak_value": 10000.0,
            "realized_volatility": 0.5,
        }
        decision = await agent.think(context)
        # Multiple breaches including drawdown → CRITICAL
        assert decision.decision_type == DecisionType.KILL_SWITCH

    @pytest.mark.asyncio
    async def test_exposure_breach(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Total exposure breach → RISK_ALERT."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            exposure_limit=0.1,  # 10%
            max_position_size=1.0,  # Very high so position size doesn't trigger
            var_limit=1.0,  # Very high so VaR doesn't trigger
        )
        await agent.start()
        context = {
            "portfolio_value": 10000.0,
            "exposure_by_asset": {"SOL/USDC": 3000.0, "BTC/USDC": 3000.0},
            "peak_value": 10000.0,
        }
        decision = await agent.think(context)
        assert decision.decision_type == DecisionType.RISK_ALERT
        assessment = decision.payload.get("assessment", {})
        assert any("exposure" in b for b in assessment.get("breached_limits", []))

    @pytest.mark.asyncio
    async def test_risk_levels(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Different breach counts produce different risk levels."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_position_size=0.01,
            max_drawdown=0.01,
            exposure_limit=0.01,
            var_limit=0.0001,
        )
        await agent.start()
        context = {
            "portfolio_value": 10000.0,
            "exposure_by_asset": {"SOL/USDC": 9000.0},
            "peak_value": 11000.0,
            "realized_volatility": 0.5,
        }
        decision = await agent.think(context)
        assessment = decision.payload.get("assessment", {})
        assert assessment["risk_level"] in ("HIGH", "CRITICAL")

    @pytest.mark.asyncio
    async def test_empty_context(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Empty context still works."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_stores_assessment(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Assessment is stored in memory."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        context = {"portfolio_value": 10000.0}
        await agent.think(context)
        stored = await agent.recall("latest_assessment")
        assert stored is not None


# ---------------------------------------------------------------------------
# Act
# ---------------------------------------------------------------------------


class TestAct:
    """Tests for act() method."""

    @pytest.mark.asyncio
    async def test_noop_does_nothing(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """NOOP decision does nothing."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        decision = AgentDecision(
            agent_id="risk-1",
            decision_type=DecisionType.NOOP,
            payload={},
        )
        await agent.act(decision)
        assert len(mock_kafka_producer.messages) == 0

    @pytest.mark.asyncio
    async def test_risk_alert_published(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """RISK_ALERT is published to Kafka."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assessment = RiskAssessment(
            portfolio_value=10000.0,
            risk_level="HIGH",
            breached_limits=["position_size"],
        )
        decision = AgentDecision(
            agent_id="risk-1",
            decision_type=DecisionType.RISK_ALERT,
            payload={"assessment": assessment.model_dump(mode="json")},
            reasoning="Position size breached",
        )
        await agent.act(decision)
        assert len(mock_kafka_producer.messages) == 1

    @pytest.mark.asyncio
    async def test_kill_switch_published(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """KILL_SWITCH publishes to Kafka and sets flag."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assessment = RiskAssessment(
            portfolio_value=10000.0,
            risk_level="CRITICAL",
            breached_limits=["drawdown"],
        )
        decision = AgentDecision(
            agent_id="risk-1",
            decision_type=DecisionType.KILL_SWITCH,
            payload={"assessment": assessment.model_dump(mode="json")},
            reasoning="Critical drawdown",
        )
        await agent.act(decision)
        assert len(mock_kafka_producer.messages) == 1

    @pytest.mark.asyncio
    async def test_kill_switch_sets_redis_flag(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """KILL_SWITCH sets global flag in Redis."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assessment = RiskAssessment(
            portfolio_value=10000.0,
            risk_level="CRITICAL",
            breached_limits=["drawdown"],
        )
        decision = AgentDecision(
            agent_id="risk-1",
            decision_type=DecisionType.KILL_SWITCH,
            payload={"assessment": assessment.model_dump(mode="json")},
            reasoning="Critical",
        )
        await agent.act(decision)
        flag = await mock_redis_manager.get("global:kill_switch")
        assert flag is not None
        if isinstance(flag, dict):
            assert flag.get("active") is True

    @pytest.mark.asyncio
    async def test_alerts_issued_counter(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Alerts issued counter increments."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assessment = RiskAssessment(risk_level="HIGH", breached_limits=["test"])
        decision = AgentDecision(
            agent_id="risk-1",
            decision_type=DecisionType.RISK_ALERT,
            payload={"assessment": assessment.model_dump(mode="json")},
        )
        assert agent._alerts_issued == 0
        await agent.act(decision)
        assert agent._alerts_issued == 1


# ---------------------------------------------------------------------------
# Kelly criterion
# ---------------------------------------------------------------------------


class TestKelly:
    """Tests for Kelly criterion position sizing."""

    def test_kelly_basic(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kelly calculation with typical values."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        size = agent.kelly_position_size(win_rate=0.55, avg_win=100.0, avg_loss=50.0)
        assert size > 0
        assert size <= 1.0

    def test_kelly_zero_loss(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kelly with zero avg_loss returns 0."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        size = agent.kelly_position_size(win_rate=0.5, avg_win=100.0, avg_loss=0.0)
        assert size == 0.0

    def test_kelly_negative(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kelly clamps negative to 0."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        size = agent.kelly_position_size(win_rate=0.3, avg_win=10.0, avg_loss=100.0)
        assert size == 0.0

    def test_kelly_capped(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kelly result is capped at 1.0 * fraction."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer, kelly_fraction=0.25)
        size = agent.kelly_position_size(win_rate=0.9, avg_win=1000.0, avg_loss=1.0)
        assert size <= 0.25

    def test_kelly_deterministic(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Same inputs give same output."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        s1 = agent.kelly_position_size(win_rate=0.6, avg_win=100.0, avg_loss=50.0)
        s2 = agent.kelly_position_size(win_rate=0.6, avg_win=100.0, avg_loss=50.0)
        assert s1 == s2


# ---------------------------------------------------------------------------
# VaR estimation
# ---------------------------------------------------------------------------


class TestVaR:
    """Tests for VaR estimation."""

    @pytest.mark.asyncio
    async def test_var_positive(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """VaR is positive for positive portfolio."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        var = await agent._estimate_var(10000.0, {"realized_volatility": 0.02})
        assert var > 0

    @pytest.mark.asyncio
    async def test_var_zero_portfolio(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """VaR is 0 for zero portfolio."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        var = await agent._estimate_var(0.0, {})
        assert var == 0.0

    @pytest.mark.asyncio
    async def test_var_uses_context(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """VaR uses realized volatility from context."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        var1 = await agent._estimate_var(10000.0, {"realized_volatility": 0.01})
        var2 = await agent._estimate_var(10000.0, {"realized_volatility": 0.05})
        assert var2 > var1

    @pytest.mark.asyncio
    async def test_var_default_vol(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """VaR uses default vol when none provided."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        var = await agent._estimate_var(10000.0, {})
        assert var > 0  # Default 2% vol gives some VaR


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


class TestKillSwitch:
    """Tests for kill switch functionality."""

    @pytest.mark.asyncio
    async def test_kill_switch_flag(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kill switch can be checked."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        active = await agent.is_kill_switch_active()
        assert active is False

    @pytest.mark.asyncio
    async def test_kill_switch_triggered(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kill switch is active after triggering."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await mock_redis_manager.set(
            "global:kill_switch",
            {"active": True, "triggered_by": "risk-1"},
        )
        active = await agent.is_kill_switch_active()
        assert active is True

    @pytest.mark.asyncio
    async def test_kill_switch_local_fallback(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Local flag used when Redis fails."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        agent._kill_switch_triggered = True
        # Make Redis fail
        async def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Redis down")
        mock_redis_manager.get = fail
        active = await agent.is_kill_switch_active()
        assert active is True


# ---------------------------------------------------------------------------
# Full cycle
# ---------------------------------------------------------------------------


class TestFullCycle:
    """Tests for run_cycle with RiskAgent."""

    @pytest.mark.asyncio
    async def test_run_cycle_all_clear(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Full cycle with all-clear."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.IDLE
        assert agent._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_run_cycle_breach(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Full cycle with breach publishes alert."""
        agent = RiskAgent(
            "risk-1", mock_redis_manager, mock_kafka_producer,
            max_drawdown=0.001,
        )
        await agent.start()
        # Store a peak value, then simulate drawdown
        await agent.remember("portfolio:state", {
            "total_value": 5000.0,
            "exposure_by_asset": {},
            "peak_value": 10000.0,
        })
        await agent.run_cycle()
        assert agent._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_health(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health report for risk agent."""
        agent = RiskAgent("risk-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        health = await agent.health()
        assert health.agent_id == "risk-1"
        assert health.state == AgentState.IDLE
