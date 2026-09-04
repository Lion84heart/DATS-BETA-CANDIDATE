"""AI Decision Engine.

Continuously analyzes live (simulated) market price ticks by running
every strategy in the modular Strategy Engine (see trading/strategies/)
independently, fusing their BUY/SELL/HOLD outputs into one final
recommendation via DecisionFusion, and persisting both — every
individual strategy result and the final fused decision — through the
existing DecisionPipeline/DecisionStore.

No LLM, no OpenAI, no Claude, no external AI API of any kind is used
anywhere in this module or the strategies it runs. Every signal is a
deterministic, rule-based technical-analysis computation over real
price/volume data.

Advisory only. This module never submits an order and never touches the
broker. DecisionPipeline.record_decision() marks every fused decision it
saves as REVIEW_REQUIRED — a human must act through the separate,
existing manual Buy/Sell flow (Paper Trading page) to execute anything
based on a recommendation.

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

from intelligence.fusion import DecisionFusion
from market.connectors.base import PriceTick
from system.decision_pipeline import DecisionPipeline, PipelineContext
from trading.base_strategy import BaseStrategy
from trading.schemas import SignalDirection, StrategySignal
from trading.strategies.atr import ATRStrategy
from trading.strategies.bollinger import BollingerBandsStrategy
from trading.strategies.ema_cross import EMACrossStrategy
from trading.strategies.rsi import RSIStrategy
from trading.strategies.support_resistance import SupportResistanceStrategy
from trading.strategies.trend_detection import TrendDetectionStrategy
from trading.strategies.volume_profile import VolumeProfileStrategy
from trading.strategies.vwap import VWAPStrategy

logger = logging.getLogger(__name__)

_MAX_BARS_PER_SYMBOL = 200
_MIN_SECONDS_BETWEEN_DECISIONS = 3.0

_RISK_VOL_LOW = 0.01
_RISK_VOL_HIGH = 0.03


def _default_strategies() -> list[BaseStrategy]:
    """The eight Strategy Engine members, each independent and self-contained."""
    return [
        RSIStrategy(),
        EMACrossStrategy(),
        VWAPStrategy(),
        ATRStrategy(),
        BollingerBandsStrategy(),
        SupportResistanceStrategy(),
        VolumeProfileStrategy(),
        TrendDetectionStrategy(),
    ]


@dataclass
class _SymbolState:
    """Rolling per-symbol bar buffer and decision-rate-limit state."""

    bars: deque = field(default_factory=lambda: deque(maxlen=_MAX_BARS_PER_SYMBOL))
    last_decision_at: float = 0.0


class AIDecisionEngine:
    """Runs the Strategy Engine on every incoming price tick and fuses it.

    Not a standalone data source: register ``on_price_tick`` as a feed
    callback (the same pattern PaperBroker uses) so the engine sees
    exactly the ticks the running paper trading session produces.
    """

    def __init__(
        self,
        pipeline: DecisionPipeline,
        strategies: list[BaseStrategy] | None = None,
        fusion: DecisionFusion | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.strategies: list[BaseStrategy] = strategies or _default_strategies()
        self.fusion = fusion or DecisionFusion()
        self._symbols: dict[str, _SymbolState] = {}
        self._decision_count = 0

    @property
    def decision_count(self) -> int:
        """Total fused decisions recorded by this engine instance."""
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

    def _run_strategy_engine(self, symbol: str, df: pd.DataFrame) -> list[StrategySignal]:
        """Run every strategy independently; each always yields a signal.

        A strategy that raises is treated as an explicit low-confidence
        HOLD rather than being silently dropped — one broken strategy
        must not shrink the vote or crash the analysis pass.
        """
        signals: list[StrategySignal] = []
        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(df, features={})
            except Exception:
                logger.exception("Strategy %s failed analyzing %s", strategy.name, symbol)
                signal = None
            if signal is None:
                signal = StrategySignal(
                    symbol=symbol,
                    direction=SignalDirection.HOLD,
                    confidence=0.0,
                    reason=f"{strategy.name} raised an error and produced no signal.",
                    strategy_name=strategy.name,
                )
            signals.append(signal)
        return signals

    def _analyze(self, symbol: str, state: _SymbolState) -> None:
        """Run one full Strategy Engine + Fusion pass and record it."""
        df = pd.DataFrame(list(state.bars))

        signals = self._run_strategy_engine(symbol, df)
        fused = self.fusion.combine(signals)
        risk_level = self._assess_risk_level(df)

        context = PipelineContext(
            symbol=symbol,
            price=float(df["close"].iloc[-1]),
            timestamp=time.time(),
            features={},
            strategy_name="decision_fusion",
        )
        record = self.pipeline.record_decision(
            context,
            reasoning=fused.reasoning,
            confidence=fused.confidence,
            signal=fused.direction.value,
            risk_level=risk_level,
        )

        # Store every individual strategy result behind this fused decision.
        self.pipeline.store.save_strategy_results(
            decision_id=record.decision_id,
            symbol=symbol,
            timestamp=record.timestamp,
            results=[
                {
                    "strategy": s.strategy_name,
                    "signal": s.direction.value,
                    "confidence": s.confidence,
                    "reasoning": s.reason,
                }
                for s in signals
            ],
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
            "strategies": [s.name for s in self.strategies],
        }
