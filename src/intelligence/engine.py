"""AI Decision Engine.

Continuously analyzes live (simulated) market price ticks and records a
BUY/SELL/HOLD recommendation — with a confidence score, human-readable
reasoning, and a risk level — for every analysis pass. Every decision is
persisted via the existing DecisionPipeline/DecisionStore.

Advisory only. This module never submits an order and never touches the
broker. DecisionPipeline.record_decision() marks every decision it saves
as REVIEW_REQUIRED — a human must act through the separate, existing
manual Buy/Sell flow (Paper Trading page) to execute anything based on a
recommendation.

The engine consumes real-time market data via the same price-tick
callback mechanism already used by PaperBroker (see
api/routers/execution.py) — it is subscribed to the running paper
trading session's simulated feed, not a separate data source.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from market.connectors.base import PriceTick
from system.decision_pipeline import DecisionPipeline, PipelineContext
from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection
from trading.strategies.momentum import MomentumStrategy

logger = logging.getLogger(__name__)

# MomentumStrategy needs 35+ bars for its MACD(12,26,9) computation to be
# meaningful; analyzing sooner would just be noise dressed up as a signal.
_MIN_BARS_FOR_STRATEGY = 35
_MAX_BARS_PER_SYMBOL = 200
_MIN_SECONDS_BETWEEN_DECISIONS = 3.0

_RISK_VOL_LOW = 0.01
_RISK_VOL_HIGH = 0.03


@dataclass
class _SymbolState:
    """Rolling per-symbol bar buffer and decision-rate-limit state."""

    bars: deque = field(default_factory=lambda: deque(maxlen=_MAX_BARS_PER_SYMBOL))
    last_decision_at: float = 0.0


class AIDecisionEngine:
    """Analyzes every incoming price tick and records a decision.

    Not a standalone data source: register ``on_price_tick`` as a feed
    callback (the same pattern PaperBroker uses) so the engine sees
    exactly the ticks the running paper trading session produces.
    """

    def __init__(
        self,
        pipeline: DecisionPipeline,
        strategy: BaseStrategy | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.strategy: BaseStrategy = strategy or MomentumStrategy()
        self._symbols: dict[str, _SymbolState] = {}
        self._decision_count = 0

    @property
    def decision_count(self) -> int:
        """Total decisions recorded by this engine instance."""
        return self._decision_count

    def on_price_tick(self, tick: PriceTick) -> None:
        """Feed callback — buffers the tick and analyzes on a rate limit.

        Never raises: a bad tick or a strategy exception must not take
        down the price feed for the broker or anything else subscribed
        to it, so all analysis errors are caught and logged.
        """
        state = self._symbols.setdefault(tick.symbol, _SymbolState())
        state.bars.append(
            {
                "timestamp": tick.timestamp,
                "open": tick.price,
                "high": tick.price,
                "low": tick.price,
                "close": tick.price,
                "volume": tick.volume,
            }
        )

        if tick.timestamp - state.last_decision_at < _MIN_SECONDS_BETWEEN_DECISIONS:
            return
        state.last_decision_at = tick.timestamp

        try:
            self._analyze(tick.symbol, state)
        except Exception:
            logger.exception("AI decision engine failed analyzing %s", tick.symbol)

    def _analyze(self, symbol: str, state: _SymbolState) -> None:
        """Run one analysis pass and record its BUY/SELL/HOLD decision."""
        df = pd.DataFrame(list(state.bars))
        n = len(df)

        if n < _MIN_BARS_FOR_STRATEGY:
            direction = SignalDirection.HOLD
            confidence = round(0.3 * (n / _MIN_BARS_FOR_STRATEGY), 2)
            reason = (
                f"Warming up: {n}/{_MIN_BARS_FOR_STRATEGY} price bars collected — "
                f"not enough history yet for {self.strategy.name} analysis."
            )
        else:
            signal = self.strategy.generate_signal(df, features={})
            if signal is not None:
                direction = signal.direction
                confidence = signal.confidence
                reason = signal.reason
            else:
                direction = SignalDirection.HOLD
                confidence = 0.5
                reason = (
                    f"No {self.strategy.name} crossover or volume confirmation on "
                    f"this bar — holding."
                )

        risk_level = self._assess_risk_level(df)

        context = PipelineContext(
            symbol=symbol,
            price=float(df["close"].iloc[-1]),
            timestamp=time.time(),
            features={},
            strategy_name=self.strategy.name,
        )
        self.pipeline.record_decision(
            context,
            reasoning=reason,
            confidence=confidence,
            signal=direction.value,
            risk_level=risk_level,
        )
        self._decision_count += 1

    @staticmethod
    def _assess_risk_level(df: pd.DataFrame) -> str:
        """Bucket recent realized volatility into LOW/MEDIUM/HIGH.

        Uses the standard deviation of the last 20 bar-to-bar returns —
        a real statistic computed from the actual simulated price path,
        not a fixed or fabricated value.
        """
        closes = df["close"]
        if len(closes) < 5:
            return "MEDIUM"  # not enough history to assess yet
        returns = closes.pct_change().dropna().tail(20)
        if returns.empty:
            return "MEDIUM"
        vol = float(returns.std() or 0.0)
        if vol < _RISK_VOL_LOW:
            return "LOW"
        if vol < _RISK_VOL_HIGH:
            return "MEDIUM"
        return "HIGH"

    def summary(self) -> dict[str, Any]:
        """Snapshot of engine activity for status/health reporting."""
        return {
            "decisions_recorded": self._decision_count,
            "symbols_tracked": list(self._symbols.keys()),
            "strategy": self.strategy.name,
        }
