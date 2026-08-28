"""Tests for agent framework Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from src.agents.schemas import (
    AgentDecision,
    AgentHealth,
    AgentMessage,
    AgentState,
    DecisionType,
    MessageType,
    OrderDetails,
    RiskAssessment,
    Signal,
    SignalDirection,
)


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------


class TestAgentState:
    """Tests for AgentState enum."""

    def test_all_states_exist(self) -> None:
        """All required states are defined."""
        states = [s.value for s in AgentState]
        assert "initializing" in states
        assert "idle" in states
        assert "thinking" in states
        assert "acting" in states
        assert "error" in states
        assert "shutdown" in states

    def test_state_count(self) -> None:
        """Exactly 6 states."""
        assert len(AgentState) == 6

    def test_state_comparison(self) -> None:
        """States can be compared."""
        assert AgentState.IDLE != AgentState.THINKING
        assert AgentState(AgentState.IDLE) == AgentState.IDLE


# ---------------------------------------------------------------------------
# SignalDirection
# ---------------------------------------------------------------------------


class TestSignalDirection:
    """Tests for SignalDirection enum."""

    def test_all_directions_exist(self) -> None:
        """All directions defined."""
        dirs = [d.value for d in SignalDirection]
        assert "BUY" in dirs
        assert "SELL" in dirs
        assert "HOLD" in dirs

    def test_direction_values(self) -> None:
        """Direction values are uppercase strings."""
        assert SignalDirection.BUY.value == "BUY"
        assert SignalDirection.SELL.value == "SELL"
        assert SignalDirection.HOLD.value == "HOLD"


# ---------------------------------------------------------------------------
# AgentMessage
# ---------------------------------------------------------------------------


class TestAgentMessage:
    """Tests for AgentMessage schema."""

    def test_valid_message(self) -> None:
        """Create a valid message."""
        msg = AgentMessage(
            from_agent="agent-1",
            to_agent="agent-2",
            message_type="signal",
            payload={"key": "value"},
        )
        assert msg.from_agent == "agent-1"
        assert msg.to_agent == "agent-2"
        assert msg.message_type == "signal"
        assert msg.payload == {"key": "value"}
        assert msg.timestamp.tzinfo is not None

    def test_broadcast_message(self) -> None:
        """Message with None to_agent is broadcast."""
        msg = AgentMessage(
            from_agent="agent-1",
            to_agent=None,
            message_type="status",
        )
        assert msg.to_agent is None

    def test_default_payload(self) -> None:
        """Default payload is empty dict."""
        msg = AgentMessage(from_agent="a", message_type="test")
        assert msg.payload == {}

    def test_timestamp_utc(self) -> None:
        """Timestamp is UTC."""
        msg = AgentMessage(from_agent="a", message_type="test")
        assert msg.timestamp.tzinfo == timezone.utc

    def test_timestamp_from_string(self) -> None:
        """Parse timestamp from ISO string."""
        ts = "2024-01-15T10:30:00+00:00"
        msg = AgentMessage(
            from_agent="a",
            message_type="test",
            timestamp=ts,
        )
        assert isinstance(msg.timestamp, datetime)

    def test_timestamp_naive_becomes_utc(self) -> None:
        """Naive datetime gets UTC tzinfo."""
        ts = datetime(2024, 1, 15, 10, 30, 0)
        msg = AgentMessage(
            from_agent="a",
            message_type="test",
            timestamp=ts,
        )
        assert msg.timestamp.tzinfo == timezone.utc

    def test_message_serialization(self) -> None:
        """Message serializes to dict."""
        msg = AgentMessage(from_agent="a", message_type="test", payload={"x": 1})
        d = msg.model_dump(mode="json")
        assert d["from_agent"] == "a"
        assert d["payload"] == {"x": 1}


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class TestSignal:
    """Tests for Signal schema."""

    def test_valid_buy_signal(self) -> None:
        """Create a valid BUY signal."""
        sig = Signal(
            symbol="SOL/USDC",
            direction=SignalDirection.BUY,
            confidence=0.8,
            reason="Bullish",
        )
        assert sig.symbol == "SOL/USDC"
        assert sig.direction == SignalDirection.BUY
        assert sig.confidence == 0.8

    def test_valid_sell_signal(self) -> None:
        """Create a valid SELL signal."""
        sig = Signal(
            symbol="ETH/USDC",
            direction=SignalDirection.SELL,
            confidence=0.6,
            reason="Bearish",
        )
        assert sig.direction == SignalDirection.SELL

    def test_confidence_min(self) -> None:
        """Confidence can be 0."""
        sig = Signal(
            symbol="X",
            direction=SignalDirection.HOLD,
            confidence=0.0,
        )
        assert sig.confidence == 0.0

    def test_confidence_max(self) -> None:
        """Confidence can be 1.0."""
        sig = Signal(
            symbol="X",
            direction=SignalDirection.HOLD,
            confidence=1.0,
        )
        assert sig.confidence == 1.0

    def test_confidence_too_high(self) -> None:
        """Confidence > 1.0 is rejected."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="X",
                direction=SignalDirection.BUY,
                confidence=1.5,
            )

    def test_confidence_negative(self) -> None:
        """Negative confidence is rejected."""
        with pytest.raises(ValidationError):
            Signal(
                symbol="X",
                direction=SignalDirection.BUY,
                confidence=-0.1,
            )

    def test_default_features_used(self) -> None:
        """Default features_used is empty dict."""
        sig = Signal(symbol="X", direction=SignalDirection.HOLD, confidence=0.5)
        assert sig.features_used == {}

    def test_features_used_roundtrip(self) -> None:
        """features_used with None values serializes correctly."""
        sig = Signal(
            symbol="X",
            direction=SignalDirection.BUY,
            confidence=0.7,
            features_used={"rsi_14": 55.0, "macd": None},
        )
        d = sig.model_dump(mode="json")
        assert d["features_used"]["rsi_14"] == 55.0
        assert d["features_used"]["macd"] is None

    def test_signal_from_dict(self, sample_signal_data: dict[str, Any]) -> None:
        """Create signal from dict."""
        sig = Signal(**sample_signal_data)
        assert sig.symbol == "SOL/USDC"
        assert sig.confidence == 0.75

    def test_signal_serialization(self, sample_signal_data: dict[str, Any]) -> None:
        """Signal serializes to JSON-safe dict."""
        sig = Signal(**sample_signal_data)
        d = sig.model_dump(mode="json")
        assert "symbol" in d
        assert "confidence" in d
        assert "timestamp" in d


# ---------------------------------------------------------------------------
# AgentDecision
# ---------------------------------------------------------------------------


class TestAgentDecision:
    """Tests for AgentDecision schema."""

    def test_valid_decision(self) -> None:
        """Create a valid decision."""
        dec = AgentDecision(
            agent_id="agent-1",
            decision_type=DecisionType.SIGNAL,
            payload={"signal": "buy"},
            reasoning="Trend is up",
            confidence=0.8,
        )
        assert dec.agent_id == "agent-1"
        assert dec.decision_type == DecisionType.SIGNAL

    def test_decision_types(self) -> None:
        """All decision types work."""
        for dt in DecisionType:
            dec = AgentDecision(agent_id="a", decision_type=dt)
            assert dec.decision_type == dt

    def test_confidence_validation(self) -> None:
        """Confidence must be in [0, 1]."""
        with pytest.raises(ValidationError):
            AgentDecision(agent_id="a", decision_type=DecisionType.NOOP, confidence=1.5)

    def test_default_reasoning(self) -> None:
        """Default reasoning is empty string."""
        dec = AgentDecision(agent_id="a", decision_type=DecisionType.NOOP)
        assert dec.reasoning == ""

    def test_timestamp_auto(self) -> None:
        """Timestamp auto-generated."""
        dec = AgentDecision(agent_id="a", decision_type=DecisionType.NOOP)
        assert dec.timestamp.tzinfo == timezone.utc

    def test_decision_serialization(self) -> None:
        """Decision serializes correctly."""
        dec = AgentDecision(
            agent_id="a",
            decision_type=DecisionType.SIGNAL,
            payload={"x": 1},
            confidence=0.5,
        )
        d = dec.model_dump(mode="json")
        assert d["agent_id"] == "a"
        assert d["confidence"] == 0.5


# ---------------------------------------------------------------------------
# AgentHealth
# ---------------------------------------------------------------------------


class TestAgentHealth:
    """Tests for AgentHealth schema."""

    def test_valid_health(self) -> None:
        """Create valid health status."""
        health = AgentHealth(
            agent_id="agent-1",
            state=AgentState.IDLE,
            error_count=0,
            tasks_completed=10,
        )
        assert health.agent_id == "agent-1"
        assert health.state == AgentState.IDLE

    def test_all_states(self) -> None:
        """All agent states are valid."""
        for state in AgentState:
            health = AgentHealth(agent_id="a", state=state)
            assert health.state == state

    def test_error_count_negative(self) -> None:
        """Negative error count rejected."""
        with pytest.raises(ValidationError):
            AgentHealth(agent_id="a", state=AgentState.IDLE, error_count=-1)

    def test_tasks_completed_negative(self) -> None:
        """Negative tasks completed rejected."""
        with pytest.raises(ValidationError):
            AgentHealth(agent_id="a", state=AgentState.IDLE, tasks_completed=-1)

    def test_default_metadata(self) -> None:
        """Default metadata is empty dict."""
        health = AgentHealth(agent_id="a", state=AgentState.IDLE)
        assert health.metadata == {}

    def test_health_serialization(self, sample_agent_health: dict[str, Any]) -> None:
        """Health serializes correctly."""
        health = AgentHealth(**sample_agent_health)
        d = health.model_dump(mode="json")
        assert d["agent_id"] == "test-agent"


# ---------------------------------------------------------------------------
# RiskAssessment
# ---------------------------------------------------------------------------


class TestRiskAssessment:
    """Tests for RiskAssessment schema."""

    def test_valid_assessment(self) -> None:
        """Create valid assessment."""
        ra = RiskAssessment(
            portfolio_value=10000.0,
            total_exposure=2000.0,
            risk_level="LOW",
        )
        assert ra.portfolio_value == 10000.0
        assert ra.risk_level == "LOW"

    def test_risk_levels(self) -> None:
        """All risk levels are valid."""
        for level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            ra = RiskAssessment(risk_level=level)
            assert ra.risk_level == level

    def test_invalid_risk_level(self) -> None:
        """Invalid risk level rejected."""
        with pytest.raises(ValidationError):
            RiskAssessment(risk_level="INVALID")

    def test_breached_limits(self) -> None:
        """Assessment with breached limits."""
        ra = RiskAssessment(
            breached_limits=["position_size", "var"],
            risk_level="HIGH",
        )
        assert len(ra.breached_limits) == 2

    def test_default_exposure_by_asset(self) -> None:
        """Default exposure_by_asset is empty."""
        ra = RiskAssessment()
        assert ra.exposure_by_asset == {}

    def test_assessment_serialization(self) -> None:
        """Assessment serializes correctly."""
        ra = RiskAssessment(
            portfolio_value=5000.0,
            current_drawdown=0.03,
            risk_level="MEDIUM",
            breached_limits=["drawdown"],
        )
        d = ra.model_dump(mode="json")
        assert d["portfolio_value"] == 5000.0
        assert d["breached_limits"] == ["drawdown"]


# ---------------------------------------------------------------------------
# OrderDetails
# ---------------------------------------------------------------------------


class TestOrderDetails:
    """Tests for OrderDetails schema."""

    def test_valid_market_buy(self) -> None:
        """Create valid market buy order."""
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.5,
            order_type="market",
        )
        assert order.symbol == "SOL/USDC"
        assert order.side == "buy"
        assert order.size == 1.5

    def test_valid_limit_sell(self) -> None:
        """Create valid limit sell order."""
        order = OrderDetails(
            symbol="ETH/USDC",
            side="sell",
            size=0.5,
            order_type="limit",
            price=3500.0,
        )
        assert order.order_type == "limit"
        assert order.price == 3500.0

    def test_size_must_be_positive(self) -> None:
        """Size must be > 0."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="buy", size=0)

    def test_size_must_be_positive_negative(self) -> None:
        """Negative size rejected."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="buy", size=-1)

    def test_invalid_side(self) -> None:
        """Invalid side rejected."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="invalid", size=1)

    def test_invalid_order_type(self) -> None:
        """Invalid order type rejected."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="buy", size=1, order_type="invalid")

    def test_invalid_execution_mode(self) -> None:
        """Invalid execution mode rejected."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="buy", size=1, execution_mode="invalid")

    def test_execution_modes(self) -> None:
        """Valid execution modes."""
        for mode in ("PAPER_TRADE", "LIVE_DRY_RUN", "LIVE_ARMED"):
            order = OrderDetails(symbol="X", side="buy", size=1, execution_mode=mode)
            assert order.execution_mode == mode

    def test_default_execution_mode(self) -> None:
        """Default execution mode is PAPER_TRADE."""
        order = OrderDetails(symbol="X", side="buy", size=1)
        assert order.execution_mode == "PAPER_TRADE"

    def test_confidence_validation(self) -> None:
        """Confidence must be in [0, 1]."""
        with pytest.raises(ValidationError):
            OrderDetails(symbol="X", side="buy", size=1, confidence=1.5)

    def test_order_serialization(self) -> None:
        """Order serializes correctly."""
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=2.0,
            confidence=0.8,
        )
        d = order.model_dump(mode="json")
        assert d["symbol"] == "SOL/USDC"
        assert d["confidence"] == 0.8

    def test_order_with_reason(self) -> None:
        """Order with reason field."""
        order = OrderDetails(
            symbol="SOL/USDC",
            side="buy",
            size=1.0,
            reason="Bullish crossover",
        )
        assert order.reason == "Bullish crossover"


# ---------------------------------------------------------------------------
# Enum round-trip
# ---------------------------------------------------------------------------


class TestEnumRoundTrip:
    """Test serialization round-trips for enums."""

    def test_agent_state_roundtrip(self) -> None:
        """AgentState survives serialization."""
        health = AgentHealth(agent_id="a", state=AgentState.THINKING)
        d = health.model_dump(mode="json")
        assert d["state"] == "thinking"

    def test_signal_direction_roundtrip(self) -> None:
        """SignalDirection survives serialization."""
        sig = Signal(symbol="X", direction=SignalDirection.SELL, confidence=0.5)
        d = sig.model_dump(mode="json")
        assert d["direction"] == "SELL"

    def test_decision_type_roundtrip(self) -> None:
        """DecisionType survives serialization."""
        dec = AgentDecision(agent_id="a", decision_type=DecisionType.KILL_SWITCH)
        d = dec.model_dump(mode="json")
        assert d["decision_type"] == "kill_switch"
