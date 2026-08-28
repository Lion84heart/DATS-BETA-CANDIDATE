"""DATS — Chain-of-Thought Reasoning Engine.

Provides deterministic, rule-based reasoning for trading decisions.
No external LLM calls — fully auditable and reproducible.
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reasoning chain models
# ---------------------------------------------------------------------------


class Observation(BaseModel):
    """Step 1: Raw observation of feature values."""

    features: dict[str, float | None] = Field(default_factory=dict)
    summary: str = Field(default="")


class Analysis(BaseModel):
    """Step 2: Interpretation of indicators."""

    indicators: dict[str, str] = Field(default_factory=dict)
    trend: Literal["bullish", "bearish", "neutral", "unknown"] = "unknown"
    strength: float = Field(default=0.0, ge=-1.0, le=1.0)


class Decision(BaseModel):
    """Step 3: Trading decision."""

    direction: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="")


class ReasoningChain(BaseModel):
    """Complete chain-of-thought for a trading decision."""

    observation: Observation = Field(default_factory=Observation)
    analysis: Analysis = Field(default_factory=Analysis)
    decision: Decision = Field(default_factory=Decision)
    justification: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Reasoning Engine
# ---------------------------------------------------------------------------


class ReasoningEngine:
    """Deterministic chain-of-thought reasoning for trading decisions.

    Usage::

        engine = ReasoningEngine()
        chain = await engine.analyze(features, strategy="trend_following")
        # chain.decision.direction → "BUY" | "SELL" | "HOLD"
        # chain.confidence → 0.0 … 1.0
        # chain.justification → human-readable explanation
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        features: dict[str, float | None],
        strategy: str,
    ) -> ReasoningChain:
        """Build a complete reasoning chain from features.

        Args:
            features: Dict of feature name → value (may contain None).
            strategy: One of "trend_following", "mean_reversion",
                "momentum", "breakout".

        Returns:
            A ``ReasoningChain`` with observation, analysis, decision,
            justification, and overall confidence.
        """
        observation = self._observe(features)
        analysis = self._analyze_indicators(observation)
        decision = self._decide(analysis, strategy)
        justification = self._justify(decision, analysis)

        # Overall confidence is a blend of decision confidence and
        # how many indicators were available
        available = sum(1 for v in features.values() if v is not None)
        total = max(len(features), 1)
        data_quality = available / total
        overall_confidence = round(decision.confidence * (0.5 + 0.5 * data_quality), 4)

        return ReasoningChain(
            observation=observation,
            analysis=analysis,
            decision=decision,
            justification=justification,
            confidence=overall_confidence,
        )

    # ------------------------------------------------------------------
    # Step 1: Observe
    # ------------------------------------------------------------------

    def _observe(self, features: dict[str, float | None]) -> Observation:
        """Summarise the raw feature values."""
        available = {k: v for k, v in features.items() if v is not None}
        missing = [k for k, v in features.items() if v is None]

        parts: list[str] = []
        for name, val in sorted(available.items()):
            parts.append(f"{name}={val:.4f}" if isinstance(val, float) else f"{name}={val}")

        summary = f"Available: {len(available)}/{len(features)} features"
        if missing:
            summary += f"; missing: {', '.join(missing[:5])}"
        if parts:
            summary += f"; key values: {', '.join(parts[:8])}"

        return Observation(features=available, summary=summary)

    # ------------------------------------------------------------------
    # Step 2: Analyze indicators
    # ------------------------------------------------------------------

    def _analyze_indicators(self, observation: Observation) -> Analysis:
        """Interpret technical indicators from observations."""
        f = observation.features
        indicators: dict[str, str] = {}
        trend = "neutral"
        strength = 0.0
        scores: list[float] = []

        # --- RSI ---
        rsi = f.get("rsi_14")
        if rsi is not None:
            if rsi > 70:
                indicators["rsi_14"] = f"overbought ({rsi:.1f})"
                scores.append(-0.5)
            elif rsi < 30:
                indicators["rsi_14"] = f"oversold ({rsi:.1f})"
                scores.append(0.5)
            else:
                indicators["rsi_14"] = f"neutral ({rsi:.1f})"
                scores.append(0.0)

        # --- MACD ---
        macd = f.get("macd")
        macd_signal = f.get("macd_signal")
        macd_hist = f.get("macd_histogram")
        if macd is not None and macd_signal is not None:
            if macd > macd_signal:
                indicators["macd"] = f"bullish crossover (macd={macd:.4f} > signal={macd_signal:.4f})"
                scores.append(0.4)
            else:
                indicators["macd"] = f"bearish crossover (macd={macd:.4f} < signal={macd_signal:.4f})"
                scores.append(-0.4)
        if macd_hist is not None:
            if macd_hist > 0:
                scores.append(0.2)
            else:
                scores.append(-0.2)

        # --- Bollinger %B ---
        bb_pct = f.get("bb_pct_b")
        if bb_pct is not None:
            if bb_pct > 0.8:
                indicators["bb_pct_b"] = f"near upper band ({bb_pct:.2f})"
                scores.append(-0.3)
            elif bb_pct < 0.2:
                indicators["bb_pct_b"] = f"near lower band ({bb_pct:.2f})"
                scores.append(0.3)
            else:
                indicators["bb_pct_b"] = f"mid-range ({bb_pct:.2f})"
                scores.append(0.0)

        # --- EMA ---
        ema9 = f.get("ema_9")
        ema21 = f.get("ema_21")
        ema50 = f.get("ema_50")
        close = f.get("close")
        if close is not None:
            if ema9 is not None and close > ema9:
                indicators["ema_9"] = f"price above EMA9 ({close:.2f} > {ema9:.2f})"
                scores.append(0.3)
            elif ema9 is not None:
                indicators["ema_9"] = f"price below EMA9 ({close:.2f} < {ema9:.2f})"
                scores.append(-0.3)
            if ema21 is not None and close > ema21:
                indicators["ema_21"] = f"price above EMA21"
                scores.append(0.25)
            elif ema21 is not None:
                indicators["ema_21"] = f"price below EMA21"
                scores.append(-0.25)
            if ema50 is not None:
                dist = (close - ema50) / ema50 if ema50 != 0 else 0
                indicators["ema_50"] = f"{dist*100:+.2f}% from EMA50"
                scores.append(max(-0.3, min(0.3, dist * 3)))

        # --- ADX ---
        adx = f.get("adx_14")
        if adx is not None:
            if adx > 25:
                indicators["adx_14"] = f"strong trend (ADX={adx:.1f})"
                scores.append(0.2 if sum(scores) > 0 else -0.2)
            else:
                indicators["adx_14"] = f"weak trend (ADX={adx:.1f})"

        # --- Returns ---
        ret_1m = f.get("return_1m")
        if ret_1m is not None:
            indicators["return_1m"] = f"{ret_1m*100:+.3f}%"
            scores.append(max(-0.2, min(0.2, ret_1m * 10)))

        # Aggregate
        if scores:
            strength = float(sum(scores) / len(scores))
        if strength > 0.15:
            trend = "bullish"
        elif strength < -0.15:
            trend = "bearish"
        else:
            trend = "neutral"

        return Analysis(
            indicators=indicators,
            trend=trend,  # type: ignore[arg-type]
            strength=round(strength, 4),
        )

    # ------------------------------------------------------------------
    # Step 3: Decide
    # ------------------------------------------------------------------

    def _decide(self, analysis: Analysis, strategy: str) -> Decision:
        """Generate a trading decision based on analysis and strategy."""
        trend = analysis.trend
        strength = abs(analysis.strength)

        if strategy == "trend_following":
            return self._decide_trend_following(trend, strength, analysis)
        if strategy == "mean_reversion":
            return self._decide_mean_reversion(trend, strength, analysis)
        if strategy == "momentum":
            return self._decide_momentum(trend, strength, analysis)
        if strategy == "breakout":
            return self._decide_breakout(trend, strength, analysis)

        # Unknown strategy → HOLD
        return Decision(
            direction="HOLD",
            confidence=0.0,
            rationale=f"Unknown strategy '{strategy}' — defaulting to HOLD",
        )

    def _decide_trend_following(
        self, trend: str, strength: float, analysis: Analysis
    ) -> Decision:
        """Trend-following: follow the trend direction."""
        if trend == "bullish":
            return Decision(
                direction="BUY",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Trend-following: bullish trend detected (strength={analysis.strength:.3f})",
            )
        if trend == "bearish":
            return Decision(
                direction="SELL",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Trend-following: bearish trend detected (strength={analysis.strength:.3f})",
            )
        return Decision(
            direction="HOLD",
            confidence=0.1,
            rationale="Trend-following: no clear trend — holding",
        )

    def _decide_mean_reversion(
        self, trend: str, strength: float, analysis: Analysis
    ) -> Decision:
        """Mean-reversion: trade against extreme moves."""
        # Mean reversion goes against the short-term direction
        if trend == "bullish" and strength > 0.3:
            return Decision(
                direction="SELL",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Mean-reversion: overbought conditions (strength={analysis.strength:.3f})",
            )
        if trend == "bearish" and strength > 0.3:
            return Decision(
                direction="BUY",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Mean-reversion: oversold conditions (strength={analysis.strength:.3f})",
            )
        return Decision(
            direction="HOLD",
            confidence=0.1,
            rationale="Mean-reversion: no extreme conditions detected",
        )

    def _decide_momentum(
        self, trend: str, strength: float, analysis: Analysis
    ) -> Decision:
        """Momentum: follow recent price momentum."""
        # Momentum is similar to trend-following but requires stronger signals
        if trend == "bullish" and strength > 0.2:
            return Decision(
                direction="BUY",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Momentum: upward momentum confirmed (strength={analysis.strength:.3f})",
            )
        if trend == "bearish" and strength > 0.2:
            return Decision(
                direction="SELL",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Momentum: downward momentum confirmed (strength={analysis.strength:.3f})",
            )
        return Decision(
            direction="HOLD",
            confidence=0.1,
            rationale="Momentum: insufficient momentum — holding",
        )

    def _decide_breakout(
        self, trend: str, strength: float, analysis: Analysis
    ) -> Decision:
        """Breakout: trade on strong directional moves with volume."""
        # Breakout requires strong trend + volume confirmation
        if trend == "bullish" and strength > 0.4:
            return Decision(
                direction="BUY",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Breakout: strong upward breakout (strength={analysis.strength:.3f})",
            )
        if trend == "bearish" and strength > 0.4:
            return Decision(
                direction="SELL",
                confidence=round(min(1.0, strength), 4),
                rationale=f"Breakout: strong downward breakout (strength={analysis.strength:.3f})",
            )
        return Decision(
            direction="HOLD",
            confidence=0.1,
            rationale="Breakout: no breakout conditions — holding",
        )

    # ------------------------------------------------------------------
    # Step 4: Justify
    # ------------------------------------------------------------------

    def _justify(self, decision: Decision, analysis: Analysis) -> str:
        """Produce a natural-language justification."""
        parts: list[str] = []
        parts.append(f"Decision: {decision.direction} (confidence={decision.confidence:.2f})")
        parts.append(f"Trend: {analysis.trend} (strength={analysis.strength:.3f})")
        if analysis.indicators:
            parts.append("Key indicators:")
            for name, interp in list(analysis.indicators.items())[:6]:
                parts.append(f"  - {name}: {interp}")
        parts.append(f"Rationale: {decision.rationale}")
        return "\n".join(parts)
