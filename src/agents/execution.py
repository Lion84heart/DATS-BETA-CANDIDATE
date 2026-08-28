"""DATS — Execution Agent.

Listens for trading signals, validates them, and constructs/submits
orders.  Operates in PAPER_TRADE mode by default (no real money at risk).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import BaseAgent
from agents.schemas import (
    AgentDecision,
    DecisionType,
    OrderDetails,
    Signal,
    SignalDirection,
)
from infra.kafka_client import PORTFOLIO_UPDATES
from infra.redis_client import RedisManager
from infra.kafka_client import KafkaProducer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_CONFIDENCE_THRESHOLD: float = 0.3
_DEFAULT_SIGNAL_MAX_AGE_SECONDS: int = 60
_DEFAULT_EXECUTION_MODE: str = "PAPER_TRADE"


class ExecutionAgent(BaseAgent):
    """Constructs and submits orders based on trading signals.

    Usage::

        agent = ExecutionAgent("exec-1", redis, kafka)
        await agent.start()
        await agent.run_cycle()  # processes pending signals
        await agent.stop()
    """

    def __init__(
        self,
        agent_id: str,
        redis_manager: RedisManager,
        kafka_producer: KafkaProducer,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        signal_max_age_seconds: int = _DEFAULT_SIGNAL_MAX_AGE_SECONDS,
        execution_mode: str = _DEFAULT_EXECUTION_MODE,
    ) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="execution")
        self._confidence_threshold: float = confidence_threshold
        self._signal_max_age_seconds: int = signal_max_age_seconds
        self._execution_mode: str = execution_mode
        self._orders_submitted: int = 0

    # -- Core loop overrides --------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Listen for signals, validate, build order parameters.

        Args:
            context: Current context.

        Returns:
            ``AgentDecision`` with order details, or NOOP if no valid signal.
        """
        self._log.info("ExecutionAgent %s thinking — checking for signals", self.agent_id)

        # Read pending signals from memory
        pending_signals = await self._get_pending_signals()
        if not pending_signals:
            self._log.debug("No pending signals — NOOP")
            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.NOOP,
                payload={"reason": "no_pending_signals"},
                reasoning="No pending trading signals to process.",
            )

        # Process the most recent valid signal
        for signal_data in pending_signals:
            signal = self._parse_signal(signal_data)
            if signal is None:
                continue

            # Validate signal
            validation = self._validate_signal(signal)
            if not validation["valid"]:
                self._log.warning(
                    "Signal rejected for %s: %s",
                    signal.symbol,
                    validation["reason"],
                )
                continue

            # Check kill switch
            kill_active = await self._is_kill_switch_active()
            if kill_active:
                self._log.warning("Kill switch active — blocking execution for %s", signal.symbol)
                return AgentDecision(
                    agent_id=self.agent_id,
                    decision_type=DecisionType.NOOP,
                    payload={"reason": "kill_switch_active", "signal": signal.model_dump(mode="json")},
                    reasoning="Kill switch is active — execution blocked.",
                )

            # Build order
            order = self._build_order(signal)
            self._log.info(
                "Order built for %s: %s %s @ mode=%s",
                order.symbol,
                order.side.upper(),
                order.size,
                order.execution_mode,
            )

            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.ORDER,
                payload={"order": order.model_dump(mode="json"), "signal": signal.model_dump(mode="json")},
                reasoning=f"Valid signal for {signal.symbol}: {signal.direction.value} "
                          f"(confidence={signal.confidence:.3f}). Built {order.execution_mode} order.",
                confidence=signal.confidence,
            )

        # No valid signals found
        return AgentDecision(
            agent_id=self.agent_id,
            decision_type=DecisionType.NOOP,
            payload={"reason": "no_valid_signals_after_validation"},
            reasoning="No signals passed validation.",
        )

    async def act(self, decision: AgentDecision) -> None:
        """Submit order (paper trade) and publish portfolio update.

        Args:
            decision: The decision from ``think()`` containing order details.
        """
        if decision.decision_type != DecisionType.ORDER:
            return

        order_data = decision.payload.get("order")
        signal_data = decision.payload.get("signal")
        if order_data is None:
            self._log.warning("ORDER decision has no order payload — skipping")
            return

        order = OrderDetails(**order_data)

        # Execute based on mode
        if order.execution_mode == "PAPER_TRADE":
            await self._execute_paper_trade(order)
        elif order.execution_mode == "LIVE_DRY_RUN":
            self._log.info("LIVE_DRY_RUN: Would execute %s %s %s", order.side, order.symbol, order.size)
        elif order.execution_mode == "LIVE_ARMED":
            self._log.warning("LIVE_ARMED mode not yet implemented — falling back to paper trade")
            await self._execute_paper_trade(order)
        else:
            self._log.warning("Unknown execution mode: %s", order.execution_mode)
            return

        # Publish portfolio update
        try:
            await self._kafka.send(
                PORTFOLIO_UPDATES,
                value={
                    "type": "order_executed",
                    "agent_id": self.agent_id,
                    "order": order.model_dump(mode="json"),
                    "signal": signal_data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                key=order.symbol,
            )
        except Exception as exc:
            self._log.error("Failed to publish portfolio update: %s", exc)

        # Store in memory
        try:
            await self.remember(
                f"order:{order.symbol}:{datetime.now(timezone.utc).isoformat()}",
                {
                    "order": order.model_dump(mode="json"),
                    "executed_at": datetime.now(timezone.utc).isoformat(),
                },
                ttl=86400,
            )
            await self._memory.add_episode(
                self.agent_id,
                {
                    "event": "order_executed",
                    "symbol": order.symbol,
                    "side": order.side,
                    "size": order.size,
                    "mode": order.execution_mode,
                },
            )
            self._orders_submitted += 1
        except Exception as exc:
            self._log.warning("Failed to store order in memory: %s", exc)

    # -- Signal handling ------------------------------------------------------

    async def _get_pending_signals(self) -> list[dict[str, Any]]:
        """Read pending signals from memory / inbox.

        Returns:
            List of signal dicts, newest first.
        """
        channel = f"agent:{self.agent_id}:signals"
        messages = await self._memory.get_messages(channel, limit=20)

        # Also check for signals stored directly in agent memory
        try:
            keys = await self._redis.keys(f"agent:{self.agent_id}:signal:*")
            for key in keys:
                raw = await self._redis.get(key)
                if isinstance(raw, dict) and "signal" in raw:
                    sig = raw["signal"]
                    if isinstance(sig, dict):
                        messages.append(sig)
        except Exception as exc:
            self._log.debug("Error reading signal keys: %s", exc)

        # Deduplicate by symbol + timestamp
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for msg in messages:
            key = f"{msg.get('symbol', '')}:{msg.get('timestamp', '')}"
            if key not in seen:
                seen.add(key)
                unique.append(msg)

        return unique

    def _parse_signal(self, data: dict[str, Any]) -> Signal | None:
        """Parse a raw dict into a ``Signal`` model.

        Args:
            data: Raw signal dict.

        Returns:
            Parsed ``Signal`` or ``None`` if invalid.
        """
        try:
            return Signal(**data)
        except Exception as exc:
            self._log.debug("Failed to parse signal: %s (data=%r)", exc, data)
            return None

    def _validate_signal(self, signal: Signal) -> dict[str, Any]:
        """Validate a trading signal.

        Checks:
        - Confidence above threshold
        - Signal freshness (not too old)
        - Direction is BUY or SELL (not HOLD)

        Args:
            signal: The signal to validate.

        Returns:
            Dict with ``valid`` (bool) and ``reason`` (str).
        """
        # Confidence check
        if signal.confidence < self._confidence_threshold:
            return {
                "valid": False,
                "reason": f"confidence {signal.confidence:.3f} < threshold {self._confidence_threshold}",
            }

        # Freshness check
        signal_age = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()
        if signal_age > self._signal_max_age_seconds:
            return {
                "valid": False,
                "reason": f"signal stale (age={signal_age:.0f}s > max={self._signal_max_age_seconds}s)",
            }

        # Direction check
        if signal.direction == SignalDirection.HOLD:
            return {"valid": False, "reason": "HOLD signals are not executable"}

        return {"valid": True, "reason": ""}

    # -- Order building -------------------------------------------------------

    def _build_order(self, signal: Signal) -> OrderDetails:
        """Construct order parameters from a validated signal.

        Args:
            signal: Validated trading signal.

        Returns:
            ``OrderDetails`` for execution.
        """
        # Simple position sizing: proportional to confidence
        base_size = 1.0  # Base unit
        size = base_size * signal.confidence

        # Cap at reasonable limits
        size = max(0.1, min(size, 10.0))

        side = "buy" if signal.direction == SignalDirection.BUY else "sell"

        return OrderDetails(
            symbol=signal.symbol,
            side=side,
            size=round(size, 4),
            order_type="market",
            confidence=signal.confidence,
            reason=signal.reason,
            execution_mode=self._execution_mode,  # type: ignore[arg-type]
        )

    # -- Execution ------------------------------------------------------------

    async def _execute_paper_trade(self, order: OrderDetails) -> None:
        """Execute a paper trade (simulated — no real money).

        Args:
            order: Order details.
        """
        self._log.info(
            "PAPER TRADE: %s %s %s %s (reason: %s)",
            order.side.upper(),
            order.size,
            order.symbol,
            order.order_type,
            order.reason,
        )

        # Store paper trade result
        trade_result = {
            "symbol": order.symbol,
            "side": order.side,
            "size": order.size,
            "order_type": order.order_type,
            "mode": "PAPER_TRADE",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "status": "filled",
            "fill_price": None,  # Would be set by real execution
        }

        await self.remember(
            f"paper_trade:{order.symbol}:{datetime.now(timezone.utc).isoformat()}",
            trade_result,
            ttl=86400,
        )

        # Update simulated portfolio
        try:
            portfolio = await self.recall("portfolio:state") or {}
            if not isinstance(portfolio, dict):
                portfolio = {}

            positions = portfolio.get("positions", {})
            current_pos = positions.get(order.symbol, 0.0)

            if order.side == "buy":
                new_pos = current_pos + order.size
            else:
                new_pos = current_pos - order.size

            positions[order.symbol] = round(new_pos, 4)
            portfolio["positions"] = positions
            portfolio["last_updated"] = datetime.now(timezone.utc).isoformat()

            await self.remember("portfolio:state", portfolio, ttl=3600)
        except Exception as exc:
            self._log.warning("Failed to update portfolio: %s", exc)

    # -- Risk pre-check -------------------------------------------------------

    async def _is_kill_switch_active(self) -> bool:
        """Check if the kill switch is active.

        Returns:
            ``True`` if trading should be halted.
        """
        try:
            flag = await self._redis.get("global:kill_switch")
            if isinstance(flag, dict):
                return flag.get("active", False)
        except Exception:
            pass
        return False
