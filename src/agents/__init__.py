"""DATS — Agent Framework.

Multi-agent trading system with lifecycle management, episodic/semantic
memory, chain-of-thought reasoning, and event-driven coordination.

Public API::

    from agents import (
        BaseAgent,
        StrategyAgent,
        RiskAgent,
        ExecutionAgent,
        OrchestratorAgent,
        AgentMemory,
        ReasoningEngine,
        ReasoningChain,
        AgentState,
        AgentMessage,
        Signal,
        SignalDirection,
        AgentDecision,
        AgentHealth,
        RiskAssessment,
        OrderDetails,
        DecisionType,
        MessageType,
    )
"""

from __future__ import annotations

from agents.base import BaseAgent
from agents.execution import ExecutionAgent
from agents.memory import AgentMemory
from agents.orchestrator import OrchestratorAgent
from agents.reasoning import ReasoningChain, ReasoningEngine
from agents.risk import RiskAgent
from agents.schemas import (
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
from agents.strategy import StrategyAgent

__all__ = [
    # Base
    "BaseAgent",
    # Agent types
    "StrategyAgent",
    "RiskAgent",
    "ExecutionAgent",
    "OrchestratorAgent",
    # Memory
    "AgentMemory",
    # Reasoning
    "ReasoningEngine",
    "ReasoningChain",
    # Schemas
    "AgentState",
    "AgentMessage",
    "Signal",
    "SignalDirection",
    "AgentDecision",
    "AgentHealth",
    "RiskAssessment",
    "OrderDetails",
    "DecisionType",
    "MessageType",
]
