"""DATS — Risk Agent.

Monitors risk metrics and enforces limits.  Checks portfolio exposure,
drawdown levels, and VaR.  Publishes risk alerts and can trigger a
kill-switch when critical thresholds are breached.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import BaseAgent
from agents.schemas import (
    AgentDecision,
    DecisionType,
    RiskAssessment,
)
from infra.kafka_client import RISK_ALERTS
from infra.redis_client import RedisManager
from infra.kafka_client import KafkaProducer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (overridden by config)
# ---------------------------------------------------------------------------

_DEFAULT_MAX_POSITION_SIZE: float = 0.10  # 10% of portfolio
_DEFAULT_MAX_DRAWDOWN: float = 0.05       # 5% max drawdown
_DEFAULT_VAR_LIMIT: float = 0.02          # 2% daily VaR
_DEFAULT_EXPOSURE_LIMIT: float = 0.15     # 15% single-asset
_DEFAULT_KELLY_FRACTION: float = 0.25     # Quarter-Kelly


class RiskAgent(BaseAgent):
    """Monitors risk and enforces limits.

    Usage::

        agent = RiskAgent("risk-1", redis, kafka)
        await agent.start()
        await agent.run_cycle()  # checks risk → publishes alerts if needed
        await agent.stop()
    """

    def __init__(
        self,
        agent_id: str,
        redis_manager: RedisManager,
        kafka_producer: KafkaProducer,
        max_position_size: float | None = None,
        max_drawdown: float | None = None,
        var_limit: float | None = None,
        exposure_limit: float | None = None,
        kelly_fraction: float = _DEFAULT_KELLY_FRACTION,
    ) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="risk")
        cfg = self._settings

        self.max_position_size: float = (
            max_position_size
            if max_position_size is not None
            else getattr(cfg.trading, "max_position_size", _DEFAULT_MAX_POSITION_SIZE)
        )
        self.max_drawdown: float = (
            max_drawdown
            if max_drawdown is not None
            else getattr(cfg, "risk", {}).get("max_drawdown", _DEFAULT_MAX_DRAWDOWN)
            if hasattr(cfg, "risk")
            else _DEFAULT_MAX_DRAWDOWN
        )
        self.var_limit: float = (
            var_limit
            if var_limit is not None
            else getattr(cfg, "risk", {}).get("var_limit", _DEFAULT_VAR_LIMIT)
            if hasattr(cfg, "risk")
            else _DEFAULT_VAR_LIMIT
        )
        self.exposure_limit: float = (
            exposure_limit
            if exposure_limit is not None
            else getattr(cfg, "risk", {}).get("exposure_limit", _DEFAULT_EXPOSURE_LIMIT)
            if hasattr(cfg, "risk")
            else _DEFAULT_EXPOSURE_LIMIT
        )
        self.kelly_fraction: float = kelly_fraction
        self._alerts_issued: int = 0
        self._kill_switch_triggered: bool = False

    # -- Core loop overrides --------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Check risk metrics and decide whether to alert.

        Args:
            context: Current context with portfolio data.

        Returns:
            ``AgentDecision`` with risk assessment, or NOOP if all clear.
        """
        self._log.info("RiskAgent %s thinking — checking risk metrics", self.agent_id)

        # Build risk assessment
        assessment = await self._build_assessment(context)

        # Store assessment in memory
        await self.remember(
            "latest_assessment",
            assessment.model_dump(mode="json"),
            ttl=300,
        )

        # Check if any limits are breached
        if assessment.breached_limits:
            self._log.warning(
                "Risk limits breached: %s (level=%s)",
                assessment.breached_limits,
                assessment.risk_level,
            )

            if assessment.risk_level == "CRITICAL":
                return AgentDecision(
                    agent_id=self.agent_id,
                    decision_type=DecisionType.KILL_SWITCH,
                    payload={"assessment": assessment.model_dump(mode="json")},
                    reasoning=f"CRITICAL risk: {', '.join(assessment.breached_limits)}. "
                              f"Kill switch activated.",
                    confidence=1.0,
                )

            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.RISK_ALERT,
                payload={"assessment": assessment.model_dump(mode="json")},
                reasoning=f"Risk limits breached: {', '.join(assessment.breached_limits)}",
                confidence=min(1.0, len(assessment.breached_limits) * 0.3 + 0.3),
            )

        # All clear
        self._log.debug("All risk metrics within limits (level=%s)", assessment.risk_level)
        return AgentDecision(
            agent_id=self.agent_id,
            decision_type=DecisionType.NOOP,
            payload={"assessment": assessment.model_dump(mode="json")},
            reasoning="All risk metrics within acceptable limits.",
        )

    async def act(self, decision: AgentDecision) -> None:
        """Publish risk alerts or kill switch signals.

        Args:
            decision: The decision from ``think()``.
        """
        if decision.decision_type == DecisionType.NOOP:
            return

        if decision.decision_type == DecisionType.KILL_SWITCH:
            await self._publish_kill_switch(decision)
            return

        if decision.decision_type == DecisionType.RISK_ALERT:
            await self._publish_risk_alert(decision)
            return

    # -- Risk assessment ------------------------------------------------------

    async def _build_assessment(self, context: dict[str, Any]) -> RiskAssessment:
        """Build a complete risk assessment from context and memory."""
        portfolio_value = context.get("portfolio_value", 0.0)
        exposure_by_asset: dict[str, float] = context.get("exposure_by_asset", {})

        # Try to read portfolio from memory if not in context
        if not portfolio_value:
            try:
                portfolio = await self.recall("portfolio:state")
                if isinstance(portfolio, dict):
                    portfolio_value = portfolio.get("total_value", 0.0)
                    exposure_by_asset = portfolio.get("exposure_by_asset", {})
            except Exception as exc:
                self._log.debug("Could not read portfolio state: %s", exc)

        total_exposure = sum(abs(v) for v in exposure_by_asset.values())

        # Calculate drawdown
        peak_value = context.get("peak_value", portfolio_value)
        if peak_value is None:
            peak_value = portfolio_value
        current_drawdown = 0.0
        if peak_value and peak_value > 0 and portfolio_value < peak_value:
            current_drawdown = (peak_value - portfolio_value) / peak_value

        # Simple VaR estimate (parametric, 95% confidence)
        var_estimate = await self._estimate_var(portfolio_value, context)

        # Determine breached limits
        breached: list[str] = []
        risk_level = "LOW"

        # Position size check
        max_pos = 0.0
        for asset, exposure in exposure_by_asset.items():
            if portfolio_value > 0:
                pos_pct = abs(exposure) / portfolio_value
                if pos_pct > self.max_position_size:
                    breached.append(f"position_size:{asset}({pos_pct:.2%}>{self.max_position_size:.2%})")
                max_pos = max(max_pos, pos_pct)

        # Exposure check
        if portfolio_value > 0:
            total_exposure_pct = total_exposure / portfolio_value
            if total_exposure_pct > self.exposure_limit:
                breached.append(f"total_exposure({total_exposure_pct:.2%}>{self.exposure_limit:.2%})")

        # Drawdown check
        if current_drawdown > self.max_drawdown:
            breached.append(f"drawdown({current_drawdown:.2%}>{self.max_drawdown:.2%})")

        # VaR check
        if portfolio_value > 0:
            var_pct = var_estimate / portfolio_value
            if var_pct > self.var_limit:
                breached.append(f"var({var_pct:.2%}>{self.var_limit:.2%})")

        # Determine risk level
        if len(breached) >= 3 or ("drawdown" in str(breached) and current_drawdown > self.max_drawdown * 3.0):
            risk_level = "CRITICAL"
        elif len(breached) >= 2:
            risk_level = "HIGH"
        elif len(breached) == 1:
            risk_level = "MEDIUM"

        return RiskAssessment(
            portfolio_value=portfolio_value,
            total_exposure=total_exposure,
            max_position_size=self.max_position_size,
            current_drawdown=current_drawdown,
            max_drawdown_limit=self.max_drawdown,
            var_estimate=var_estimate,
            var_limit=self.var_limit,
            exposure_by_asset=exposure_by_asset,
            risk_level=risk_level,  # type: ignore[arg-type]
            breached_limits=breached,
        )

    async def _estimate_var(self, portfolio_value: float, context: dict[str, Any]) -> float:
        """Estimate daily VaR (parametric, 95%).

        Uses realized volatility from context if available,
        otherwise falls back to a conservative estimate.
        """
        realized_vol = context.get("realized_volatility", 0.0)
        returns_std = context.get("returns_std", 0.0)

        # Try to read from memory
        if not realized_vol:
            try:
                vol_data = await self.recall("market:volatility")
                if isinstance(vol_data, dict):
                    realized_vol = vol_data.get("realized_vol_20", 0.0)
            except Exception:
                pass

        vol = realized_vol or returns_std or 0.02  # Default 2% daily vol
        # 95% confidence z-score ≈ 1.645
        z_score = 1.645
        var = portfolio_value * vol * z_score
        return round(var, 2)

    def kelly_position_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> float:
        """Calculate fractional Kelly position size.

        Args:
            win_rate: Probability of winning (0–1).
            avg_win: Average win amount.
            avg_loss: Average loss amount.

        Returns:
            Fraction of portfolio to allocate.
        """
        if avg_loss == 0:
            return 0.0
        kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss
        kelly = max(0.0, min(kelly, 1.0))  # Clamp to [0, 1]
        return kelly * self.kelly_fraction

    # -- Publishing -----------------------------------------------------------

    async def _publish_risk_alert(self, decision: AgentDecision) -> None:
        """Publish a risk alert to Kafka."""
        assessment_data = decision.payload.get("assessment", {})
        try:
            result = await self._kafka.send(
                RISK_ALERTS,
                value={
                    "type": "risk_alert",
                    "agent_id": self.agent_id,
                    "assessment": assessment_data,
                    "reasoning": decision.reasoning,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                key="risk",
            )
            self._alerts_issued += 1
            self._log.info(
                "Risk alert published (partition=%s, offset=%s)",
                result.get("partition"),
                result.get("offset"),
            )

            # Store in memory
            await self._memory.add_episode(
                self.agent_id,
                {
                    "event": "risk_alert",
                    "risk_level": assessment_data.get("risk_level"),
                    "breached_limits": assessment_data.get("breached_limits"),
                },
            )
        except Exception as exc:
            self._log.error("Failed to publish risk alert: %s", exc)

    async def _publish_kill_switch(self, decision: AgentDecision) -> None:
        """Publish a kill-switch signal to halt trading."""
        assessment_data = decision.payload.get("assessment", {})
        try:
            # Publish to risk alerts topic with kill flag
            result = await self._kafka.send(
                RISK_ALERTS,
                value={
                    "type": "kill_switch",
                    "agent_id": self.agent_id,
                    "assessment": assessment_data,
                    "reasoning": decision.reasoning,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                key="kill",
            )
            self._kill_switch_triggered = True
            self._alerts_issued += 1
            self._log.critical(
                "KILL SWITCH ACTIVATED (partition=%s, offset=%s)",
                result.get("partition"),
                result.get("offset"),
            )

            # Set a persistent flag in Redis
            await self.remember(
                "kill_switch:active",
                {
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "reason": decision.reasoning,
                    "assessment": assessment_data,
                },
                ttl=3600,  # 1 hour — must be manually cleared
            )

            # Also set global kill flag
            await self._redis.set(
                "global:kill_switch",
                {
                    "active": True,
                    "triggered_by": self.agent_id,
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                },
                ttl=3600,
            )

            await self._memory.add_episode(
                self.agent_id,
                {
                    "event": "kill_switch",
                    "risk_level": "CRITICAL",
                    "breached_limits": assessment_data.get("breached_limits"),
                },
            )
        except Exception as exc:
            self._log.error("Failed to publish kill switch: %s", exc)

    async def is_kill_switch_active(self) -> bool:
        """Check whether the kill switch is currently active.

        Returns:
            ``True`` if the kill switch has been triggered.
        """
        try:
            flag = await self._redis.get("global:kill_switch")
            if isinstance(flag, dict):
                return flag.get("active", False)
            return False
        except Exception:
            return self._kill_switch_triggered
