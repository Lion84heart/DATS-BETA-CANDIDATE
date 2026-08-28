"""DATS — Strategy Agent.

Generates trading signals from feature data using configurable rule-based
strategies.  Reads from the FeatureStore (online path), applies the
selected strategy, and publishes signals to Kafka.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.base import BaseAgent
from agents.reasoning import ReasoningEngine
from agents.schemas import (
    AgentDecision,
    DecisionType,
    Signal,
    SignalDirection,
)
from infra.kafka_client import TRADING_SIGNALS
from infra.redis_client import RedisManager
from infra.kafka_client import KafkaProducer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STRATEGY: str = "trend_following"
_SUPPORTED_STRATEGIES: list[str] = [
    "trend_following",
    "mean_reversion",
    "momentum",
    "breakout",
]
_DEFAULT_CONFIDENCE_THRESHOLD: float = 0.3
_DEFAULT_SIGNAL_TTL: int = 300  # 5 minutes


class StrategyAgent(BaseAgent):
    """Generates trading signals from feature data.

    Usage::

        agent = StrategyAgent("strat-1", redis, kafka, feature_store)
        await agent.start()
        await agent.run_cycle()  # reads features → thinks → publishes signal
        await agent.stop()
    """

    def __init__(
        self,
        agent_id: str,
        redis_manager: RedisManager,
        kafka_producer: KafkaProducer,
        feature_store: Any,
        strategy: str = _DEFAULT_STRATEGY,
        symbols: list[str] | None = None,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        super().__init__(agent_id, redis_manager, kafka_producer, agent_type="strategy")
        self._feature_store = feature_store
        self._strategy: str = strategy
        self._symbols: list[str] = symbols or ["SOL/USDC"]
        self._confidence_threshold: float = confidence_threshold
        self._reasoning: ReasoningEngine = ReasoningEngine()
        self._signals_generated: int = 0

        if strategy not in _SUPPORTED_STRATEGIES:
            self._log.warning(
                "Strategy '%s' not in supported list %s — using default",
                strategy,
                _SUPPORTED_STRATEGIES,
            )
            self._strategy = _DEFAULT_STRATEGY

    # -- Core loop overrides --------------------------------------------------

    async def think(self, context: dict[str, Any]) -> AgentDecision:
        """Read features, apply strategy rules, generate signal.

        Args:
            context: Current context with agent metadata.

        Returns:
            ``AgentDecision`` with a ``Signal`` in the payload,
            or a NOOP decision if no signal should be generated.
        """
        self._log.info(
            "StrategyAgent %s thinking (strategy=%s, symbols=%s)",
            self.agent_id,
            self._strategy,
            self._symbols,
        )

        # Read features from FeatureStore for each symbol
        all_features: dict[str, dict[str, float | None]] = {}
        for symbol in self._symbols:
            features = await self._read_features(symbol)
            all_features[symbol] = features

        # If no features available, return NOOP
        if not any(all_features.values()):
            self._log.warning("No features available for any symbol — NOOP")
            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.NOOP,
                payload={"reason": "no_features_available"},
                reasoning="No features could be read from FeatureStore.",
            )

        # Analyze each symbol and pick the best signal
        best_signal: Signal | None = None
        best_confidence: float = -1.0

        for symbol, features in all_features.items():
            # Skip if too many features are None
            non_none = sum(1 for v in features.values() if v is not None)
            if non_none < 3:
                self._log.debug("Too few features for %s (%d/3) — skipping", symbol, non_none)
                continue

            # Run reasoning engine
            chain = await self._reasoning.analyze(features, self._strategy)

            if chain.decision.direction == "HOLD":
                self._log.debug("HOLD decision for %s (confidence=%.3f)", symbol, chain.confidence)
                continue

            # Build signal
            signal = Signal(
                symbol=symbol,
                direction=SignalDirection(chain.decision.direction),
                confidence=chain.decision.confidence,
                reason=chain.decision.rationale,
                features_used={k: v for k, v in features.items() if v is not None},
                agent_id=self.agent_id,
                strategy=self._strategy,
            )

            self._log.info(
                "Signal generated for %s: %s (confidence=%.3f)",
                symbol,
                signal.direction.value,
                signal.confidence,
            )

            if signal.confidence > best_confidence:
                best_signal = signal
                best_confidence = signal.confidence

        # If no signal met the threshold
        if best_signal is None or best_signal.confidence < self._confidence_threshold:
            return AgentDecision(
                agent_id=self.agent_id,
                decision_type=DecisionType.NOOP,
                payload={"reason": "no_signal_above_threshold"},
                reasoning=f"No signal above threshold {self._confidence_threshold}.",
            )

        return AgentDecision(
            agent_id=self.agent_id,
            decision_type=DecisionType.SIGNAL,
            payload={"signal": best_signal.model_dump(mode="json")},
            reasoning=best_signal.reason,
            confidence=best_signal.confidence,
        )

    async def act(self, decision: AgentDecision) -> None:
        """Publish signal to Kafka and store in memory.

        Args:
            decision: The decision from ``think()`` containing a signal.
        """
        if decision.decision_type != DecisionType.SIGNAL:
            self._log.debug("Decision is %s — no action needed", decision.decision_type)
            return

        signal_data = decision.payload.get("signal")
        if signal_data is None:
            self._log.warning("SIGNAL decision has no signal payload — skipping")
            return

        # Publish to Kafka
        try:
            result = await self._kafka.send(
                TRADING_SIGNALS,
                value=signal_data,
                key=signal_data.get("symbol", "unknown"),
            )
            self._log.info(
                "Signal published to %s (partition=%s, offset=%s)",
                TRADING_SIGNALS,
                result.get("partition"),
                result.get("offset"),
            )
        except Exception as exc:
            self._log.error("Failed to publish signal: %s", exc)
            return

        # Store in agent memory
        try:
            await self.remember(
                f"signal:{signal_data.get('symbol', 'unknown')}",
                {
                    "signal": signal_data,
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "kafka_result": result,
                },
                ttl=_DEFAULT_SIGNAL_TTL,
            )
            await self._memory.add_episode(
                self.agent_id,
                {
                    "event": "signal_published",
                    "symbol": signal_data.get("symbol"),
                    "direction": signal_data.get("direction"),
                    "confidence": signal_data.get("confidence"),
                },
            )
            self._signals_generated += 1
        except Exception as exc:
            self._log.warning("Failed to store signal in memory: %s", exc)

    # -- Internal helpers -----------------------------------------------------

    async def _read_features(self, symbol: str) -> dict[str, float | None]:
        """Read all relevant features from the online FeatureStore.

        Args:
            symbol: Trading symbol.

        Returns:
            Dict of feature name → value (None if unavailable).
        """
        # Key features we need for signal generation
        feature_names = [
            "rsi_14", "rsi_7",
            "macd", "macd_signal", "macd_histogram",
            "bb_upper", "bb_lower", "bb_pct_b",
            "ema_9", "ema_21", "ema_50",
            "sma_20", "sma_50",
            "atr_14",
            "adx_14", "plus_di", "minus_di",
            "relative_volume",
            "return_1m",
            "z_score",
            "dist_from_ema50",
        ]

        features: dict[str, float | None] = {}
        for feat in feature_names:
            try:
                value = await self._feature_store.get_online(symbol, feat)
                features[feat] = value
            except Exception as exc:
                self._log.debug("Feature %s not available for %s: %s", feat, symbol, exc)
                features[feat] = None

        # Also try to get current "close" price
        try:
            close = await self._feature_store.get_online(symbol, "close")
            if close is not None:
                features["close"] = close
        except Exception:
            features["close"] = None

        available = sum(1 for v in features.values() if v is not None)
        self._log.debug(
            "Read %d/%d features for %s",
            available,
            len(features),
            symbol,
        )
        return features
