"""Tests for ExecutionAgent: signal validation, order building."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from src.agents.execution import ExecutionAgent
from src.agents.schemas import AgentDecision, AgentState, DecisionType, OrderDetails, Signal, SignalDirection


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """Tests for ExecutionAgent construction."""

    def test_defaults(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Default parameters."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        assert agent.agent_type == "execution"
        assert agent._execution_mode == "PAPER_TRADE"
        assert agent._confidence_threshold == 0.3

    def test_custom_params(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Custom parameters."""
        agent = ExecutionAgent(
            "exec-1", mock_redis_manager, mock_kafka_producer,
            confidence_threshold=0.5,
            signal_max_age_seconds=30,
            execution_mode="LIVE_DRY_RUN",
        )
        assert agent._confidence_threshold == 0.5
        assert agent._signal_max_age_seconds == 30
        assert agent._execution_mode == "LIVE_DRY_RUN"


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    """Tests for ExecutionAgent lifecycle."""

    @pytest.mark.asyncio
    async def test_start(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """ExecutionAgent starts correctly."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_stop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """ExecutionAgent stops correctly."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.stop()
        assert agent.state == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Works as async context manager."""
        async with ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer) as agent:
            assert agent.state == AgentState.IDLE


# ---------------------------------------------------------------------------
# Signal validation
# ---------------------------------------------------------------------------


class TestSignalValidation:
    """Tests for signal validation logic."""

    def test_valid_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Valid signal passes validation."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
        )
        result = agent._validate_signal(signal)
        assert result["valid"] is True

    def test_low_confidence_rejected(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Signal below confidence threshold rejected."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer, confidence_threshold=0.9)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.5,
        )
        result = agent._validate_signal(signal)
        assert result["valid"] is False
        assert "confidence" in result["reason"]

    def test_stale_signal_rejected(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Old signal rejected."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer, signal_max_age_seconds=1)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
            timestamp=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        result = agent._validate_signal(signal)
        assert result["valid"] is False
        assert "stale" in result["reason"] or "age" in result["reason"]

    def test_hold_rejected(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """HOLD signal rejected."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.HOLD,
            confidence=0.8,
        )
        result = agent._validate_signal(signal)
        assert result["valid"] is False
        assert "HOLD" in result["reason"]

    def test_fresh_signal_accepted(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Fresh signal accepted."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer, signal_max_age_seconds=60)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
            timestamp=datetime.now(timezone.utc),
        )
        result = agent._validate_signal(signal)
        assert result["valid"] is True


# ---------------------------------------------------------------------------
# Order building
# ---------------------------------------------------------------------------


class TestOrderBuilding:
    """Tests for order parameter construction."""

    def test_buy_order(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """BUY signal produces buy order."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
        )
        order = agent._build_order(signal)
        assert order.symbol == "SOL/USDC"
        assert order.side == "buy"
        assert order.size > 0

    def test_sell_order(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """SELL signal produces sell order."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.SELL,
            confidence=0.8,
        )
        order = agent._build_order(signal)
        assert order.side == "sell"

    def test_size_proportional_to_confidence(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Order size is proportional to confidence."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal_low = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=0.3)
        signal_high = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=0.9)
        order_low = agent._build_order(signal_low)
        order_high = agent._build_order(signal_high)
        assert order_high.size > order_low.size

    def test_size_capped(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Order size is capped at maximum."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=1.0)
        order = agent._build_order(signal)
        assert order.size <= 10.0

    def test_size_minimum(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Order size has a minimum."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=0.01)
        order = agent._build_order(signal)
        assert order.size >= 0.1

    def test_market_order_default(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Default order type is market."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=0.8)
        order = agent._build_order(signal)
        assert order.order_type == "market"

    def test_order_includes_reason(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Order includes signal reason."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        signal = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
            reason="Bullish crossover",
        )
        order = agent._build_order(signal)
        assert order.reason == "Bullish crossover"

    def test_execution_mode_propagated(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Execution mode is set from agent config."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer, execution_mode="LIVE_DRY_RUN")
        signal = Signal(symbol="SOL/USDC", direction=SignalDirection.BUY, confidence=0.8)
        order = agent._build_order(signal)
        assert order.execution_mode == "LIVE_DRY_RUN"


# ---------------------------------------------------------------------------
# Think
# ---------------------------------------------------------------------------


class TestThink:
    """Tests for think() method."""

    @pytest.mark.asyncio
    async def test_no_signals_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """No pending signals → NOOP."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_with_valid_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any, sample_signal_data: dict[str, Any]) -> None:
        """Valid signal produces ORDER decision."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        # Publish signal to agent's inbox
        await agent._memory.publish_message(
            f"agent:exec-1:signals",
            sample_signal_data,
        )
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.ORDER
        assert "order" in decision.payload

    @pytest.mark.asyncio
    async def test_invalid_signal_noop(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Invalid signal → NOOP after validation."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer, confidence_threshold=0.99)
        await agent.start()
        signal_data = {
            "symbol": "SOL/USDC",
            "direction": "BUY",
            "confidence": 0.1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await agent._memory.publish_message(f"agent:exec-1:signals", signal_data)
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self, mock_redis_manager: Any, mock_kafka_producer: Any, sample_signal_data: dict[str, Any]) -> None:
        """Kill switch blocks execution."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await mock_redis_manager.set("global:kill_switch", {"active": True})
        await agent._memory.publish_message(f"agent:exec-1:signals", sample_signal_data)
        decision = await agent.think({})
        assert decision.decision_type == DecisionType.NOOP
        assert "kill_switch" in decision.payload.get("reason", "")


# ---------------------------------------------------------------------------
# Act
# ---------------------------------------------------------------------------


class TestAct:
    """Tests for act() method."""

    @pytest.mark.asyncio
    async def test_noop_does_nothing(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """NOOP does nothing."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        decision = AgentDecision(agent_id="exec-1", decision_type=DecisionType.NOOP, payload={})
        await agent.act(decision)
        assert len(mock_kafka_producer.messages) == 0

    @pytest.mark.asyncio
    async def test_order_executes_paper_trade(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """ORDER decision executes paper trade."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.0,
            execution_mode="PAPER_TRADE",
        )
        decision = AgentDecision(
            agent_id="exec-1",
            decision_type=DecisionType.ORDER,
            payload={"order": order.model_dump(mode="json"), "signal": {}},
        )
        await agent.act(decision)
        assert len(mock_kafka_producer.messages) >= 1

    @pytest.mark.asyncio
    async def test_order_publishes_portfolio_update(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """ORDER publishes portfolio update to Kafka."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.0,
            execution_mode="PAPER_TRADE",
        )
        decision = AgentDecision(
            agent_id="exec-1",
            decision_type=DecisionType.ORDER,
            payload={"order": order.model_dump(mode="json"), "signal": {}},
        )
        await agent.act(decision)
        topics = [m["topic"] for m in mock_kafka_producer.messages]
        from src.infra.kafka_client import PORTFOLIO_UPDATES
        assert PORTFOLIO_UPDATES in topics

    @pytest.mark.asyncio
    async def test_live_dry_run(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """LIVE_DRY_RUN mode logs but doesn't execute."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.0,
            execution_mode="LIVE_DRY_RUN",
        )
        decision = AgentDecision(
            agent_id="exec-1",
            decision_type=DecisionType.ORDER,
            payload={"order": order.model_dump(mode="json"), "signal": {}},
        )
        await agent.act(decision)
        # Should still publish portfolio update
        assert len(mock_kafka_producer.messages) >= 1

    @pytest.mark.asyncio
    async def test_missing_order_payload(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Missing order payload handled gracefully."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        decision = AgentDecision(
            agent_id="exec-1",
            decision_type=DecisionType.ORDER,
            payload={},
        )
        await agent.act(decision)  # Should not raise

    @pytest.mark.asyncio
    async def test_order_stored_in_memory(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Executed order stored in memory."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.0,
            execution_mode="PAPER_TRADE",
        )
        decision = AgentDecision(
            agent_id="exec-1",
            decision_type=DecisionType.ORDER,
            payload={"order": order.model_dump(mode="json"), "signal": {}},
        )
        await agent.act(decision)
        assert agent._orders_submitted == 1


# ---------------------------------------------------------------------------
# Paper trade execution
# ---------------------------------------------------------------------------


class TestPaperTrade:
    """Tests for paper trade execution."""

    @pytest.mark.asyncio
    async def test_paper_trade_stores_result(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Paper trade stores result in memory."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(symbol="SOL/USDC", side="buy", size=1.0, execution_mode="PAPER_TRADE")
        await agent._execute_paper_trade(order)
        # Check that paper trade was stored
        keys = await mock_redis_manager.keys("agent:exec-1:paper_trade:*")
        assert len(keys) >= 1

    @pytest.mark.asyncio
    async def test_paper_trade_updates_portfolio(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Paper trade updates simulated portfolio."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        order = OrderDetails(symbol="SOL/USDC", side="buy", size=1.0, execution_mode="PAPER_TRADE")
        await agent._execute_paper_trade(order)
        portfolio = await agent.recall("portfolio:state")
        assert portfolio is not None
        if isinstance(portfolio, dict):
            assert "positions" in portfolio
            assert portfolio["positions"]["SOL/USDC"] == 1.0

    @pytest.mark.asyncio
    async def test_paper_trade_sell_reduces_position(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Sell reduces position."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        # First buy
        buy_order = OrderDetails(symbol="SOL/USDC", side="buy", size=2.0, execution_mode="PAPER_TRADE")
        await agent._execute_paper_trade(buy_order)
        # Then sell
        sell_order = OrderDetails(symbol="SOL/USDC", side="sell", size=1.0, execution_mode="PAPER_TRADE")
        await agent._execute_paper_trade(sell_order)
        portfolio = await agent.recall("portfolio:state")
        if isinstance(portfolio, dict):
            assert portfolio["positions"]["SOL/USDC"] == 1.0


# ---------------------------------------------------------------------------
# Kill switch check
# ---------------------------------------------------------------------------


class TestKillSwitchCheck:
    """Tests for kill switch checking."""

    @pytest.mark.asyncio
    async def test_kill_switch_inactive(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kill switch is inactive by default."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        active = await agent._is_kill_switch_active()
        assert active is False

    @pytest.mark.asyncio
    async def test_kill_switch_active(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kill switch is active when set."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await mock_redis_manager.set("global:kill_switch", {"active": True})
        active = await agent._is_kill_switch_active()
        assert active is True

    @pytest.mark.asyncio
    async def test_kill_switch_redis_failure(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Kill switch check handles Redis failure."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        async def fail(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("Redis down")
        mock_redis_manager.get = fail
        active = await agent._is_kill_switch_active()
        assert active is False


# ---------------------------------------------------------------------------
# Full cycle
# ---------------------------------------------------------------------------


class TestFullCycle:
    """Tests for run_cycle with ExecutionAgent."""

    @pytest.mark.asyncio
    async def test_run_cycle_no_signals(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Full cycle with no signals."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent.run_cycle()
        assert agent.state == AgentState.IDLE

    @pytest.mark.asyncio
    async def test_run_cycle_with_signal(self, mock_redis_manager: Any, mock_kafka_producer: Any, sample_signal_data: dict[str, Any]) -> None:
        """Full cycle with valid signal."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        await agent._memory.publish_message(f"agent:exec-1:signals", sample_signal_data)
        await agent.run_cycle()
        assert agent.state == AgentState.IDLE
        assert agent._tasks_completed == 1

    @pytest.mark.asyncio
    async def test_health(self, mock_redis_manager: Any, mock_kafka_producer: Any) -> None:
        """Health report."""
        agent = ExecutionAgent("exec-1", mock_redis_manager, mock_kafka_producer)
        await agent.start()
        health = await agent.health()
        assert health.agent_id == "exec-1"
        assert health.state == AgentState.IDLE
