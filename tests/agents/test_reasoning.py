"""Tests for ReasoningEngine (chain-of-thought, confidence scoring)."""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.reasoning import (
    Analysis,
    Decision,
    Observation,
    ReasoningChain,
    ReasoningEngine,
)


# ---------------------------------------------------------------------------
# ReasoningChain model
# ---------------------------------------------------------------------------


class TestReasoningChain:
    """Tests for ReasoningChain Pydantic model."""

    def test_default_chain(self) -> None:
        """Default chain has all fields."""
        chain = ReasoningChain()
        assert chain.observation is not None
        assert chain.analysis is not None
        assert chain.decision is not None
        assert chain.confidence == 0.0

    def test_chain_with_values(self) -> None:
        """Chain with explicit values."""
        chain = ReasoningChain(
            observation=Observation(features={"rsi": 50.0}, summary="test"),
            analysis=Analysis(trend="bullish", strength=0.5),
            decision=Decision(direction="BUY", confidence=0.8),
            justification="Test justification",
            confidence=0.8,
        )
        assert chain.decision.direction == "BUY"
        assert chain.confidence == 0.8


# ---------------------------------------------------------------------------
# Observation step
# ---------------------------------------------------------------------------


class TestObserve:
    """Tests for the _observe step."""

    def test_observe_with_features(self, sample_features: dict[str, float]) -> None:
        """Observe extracts available features."""
        engine = ReasoningEngine()
        obs = engine._observe(sample_features)
        assert len(obs.features) == len(sample_features)
        assert "rsi_14" in obs.features
        assert "Available" in obs.summary

    def test_observe_with_none(self) -> None:
        """Observe handles None values."""
        engine = ReasoningEngine()
        features = {"rsi_14": 55.0, "macd": None, "close": 100.0}
        obs = engine._observe(features)
        assert "rsi_14" in obs.features
        assert "macd" not in obs.features
        assert "missing" in obs.summary.lower() or "macd" in obs.summary

    def test_observe_empty(self) -> None:
        """Observe with empty features."""
        engine = ReasoningEngine()
        obs = engine._observe({})
        assert obs.features == {}
        assert "Available: 0" in obs.summary


# ---------------------------------------------------------------------------
# Analysis step
# ---------------------------------------------------------------------------


class TestAnalyzeIndicators:
    """Tests for the _analyze_indicators step."""

    def test_bullish_analysis(self, sample_features: dict[str, float]) -> None:
        """Bullish features produce bullish analysis."""
        engine = ReasoningEngine()
        obs = engine._observe(sample_features)
        analysis = engine._analyze_indicators(obs)
        assert analysis.trend == "bullish"
        assert analysis.strength > 0
        assert len(analysis.indicators) > 0

    def test_bearish_analysis(self, sample_bearish_features: dict[str, float]) -> None:
        """Bearish features produce bearish analysis."""
        engine = ReasoningEngine()
        obs = engine._observe(sample_bearish_features)
        analysis = engine._analyze_indicators(obs)
        assert analysis.trend == "bearish"
        assert analysis.strength < 0

    def test_rsi_overbought(self) -> None:
        """RSI > 70 is overbought."""
        engine = ReasoningEngine()
        obs = Observation(features={"rsi_14": 75.0})
        analysis = engine._analyze_indicators(obs)
        assert "rsi_14" in analysis.indicators
        assert "overbought" in analysis.indicators["rsi_14"]

    def test_rsi_oversold(self) -> None:
        """RSI < 30 is oversold."""
        engine = ReasoningEngine()
        obs = Observation(features={"rsi_14": 25.0})
        analysis = engine._analyze_indicators(obs)
        assert "oversold" in analysis.indicators["rsi_14"]

    def test_rsi_neutral(self) -> None:
        """RSI 30-70 is neutral."""
        engine = ReasoningEngine()
        obs = Observation(features={"rsi_14": 50.0})
        analysis = engine._analyze_indicators(obs)
        assert "neutral" in analysis.indicators["rsi_14"]

    def test_macd_bullish(self) -> None:
        """MACD above signal is bullish."""
        engine = ReasoningEngine()
        obs = Observation(features={"macd": 0.5, "macd_signal": 0.2})
        analysis = engine._analyze_indicators(obs)
        assert "macd" in analysis.indicators
        assert "bullish" in analysis.indicators["macd"]

    def test_macd_bearish(self) -> None:
        """MACD below signal is bearish."""
        engine = ReasoningEngine()
        obs = Observation(features={"macd": -0.3, "macd_signal": 0.1})
        analysis = engine._analyze_indicators(obs)
        assert "bearish" in analysis.indicators["macd"]

    def test_bb_pct_b_high(self) -> None:
        """BB %B > 0.8 is near upper band."""
        engine = ReasoningEngine()
        obs = Observation(features={"bb_pct_b": 0.9})
        analysis = engine._analyze_indicators(obs)
        assert "upper band" in analysis.indicators.get("bb_pct_b", "")

    def test_bb_pct_b_low(self) -> None:
        """BB %B < 0.2 is near lower band."""
        engine = ReasoningEngine()
        obs = Observation(features={"bb_pct_b": 0.1})
        analysis = engine._analyze_indicators(obs)
        assert "lower band" in analysis.indicators.get("bb_pct_b", "")

    def test_empty_features(self) -> None:
        """Empty features give neutral analysis."""
        engine = ReasoningEngine()
        obs = Observation(features={})
        analysis = engine._analyze_indicators(obs)
        assert analysis.trend == "neutral"
        assert analysis.strength == 0.0

    def test_no_indicators(self) -> None:
        """Features not matching any indicator rules."""
        engine = ReasoningEngine()
        obs = Observation(features={"unknown_feature": 42.0})
        analysis = engine._analyze_indicators(obs)
        assert analysis.trend == "neutral"
        assert len(analysis.indicators) == 0


# ---------------------------------------------------------------------------
# Decision step
# ---------------------------------------------------------------------------


class TestDecide:
    """Tests for the _decide step."""

    def test_trend_following_bullish(self) -> None:
        """Trend following with bullish trend → BUY."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.5)
        decision = engine._decide(analysis, "trend_following")
        assert decision.direction == "BUY"
        assert decision.confidence > 0

    def test_trend_following_bearish(self) -> None:
        """Trend following with bearish trend → SELL."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bearish", strength=0.5)
        decision = engine._decide(analysis, "trend_following")
        assert decision.direction == "SELL"

    def test_trend_following_neutral(self) -> None:
        """Trend following with neutral → HOLD."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="neutral", strength=0.0)
        decision = engine._decide(analysis, "trend_following")
        assert decision.direction == "HOLD"

    def test_mean_reversion_overbought(self) -> None:
        """Mean reversion on bullish+strong → SELL."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.5)
        decision = engine._decide(analysis, "mean_reversion")
        assert decision.direction == "SELL"

    def test_mean_reversion_oversold(self) -> None:
        """Mean reversion on bearish+strong → BUY."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bearish", strength=0.5)
        decision = engine._decide(analysis, "mean_reversion")
        assert decision.direction == "BUY"

    def test_mean_reversion_weak(self) -> None:
        """Mean reversion with weak signal → HOLD."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.1)
        decision = engine._decide(analysis, "mean_reversion")
        assert decision.direction == "HOLD"

    def test_momentum_bullish(self) -> None:
        """Momentum with bullish → BUY."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.5)
        decision = engine._decide(analysis, "momentum")
        assert decision.direction == "BUY"

    def test_momentum_bearish(self) -> None:
        """Momentum with bearish → SELL."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bearish", strength=0.5)
        decision = engine._decide(analysis, "momentum")
        assert decision.direction == "SELL"

    def test_breakout_strong_bullish(self) -> None:
        """Breakout with strong bullish → BUY."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.5)
        decision = engine._decide(analysis, "breakout")
        assert decision.direction == "BUY"

    def test_breakout_strong_bearish(self) -> None:
        """Breakout with strong bearish → SELL."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bearish", strength=0.5)
        decision = engine._decide(analysis, "breakout")
        assert decision.direction == "SELL"

    def test_breakout_weak(self) -> None:
        """Breakout with weak signal → HOLD."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.1)
        decision = engine._decide(analysis, "breakout")
        assert decision.direction == "HOLD"

    def test_unknown_strategy(self) -> None:
        """Unknown strategy defaults to HOLD."""
        engine = ReasoningEngine()
        analysis = Analysis(trend="bullish", strength=0.8)
        decision = engine._decide(analysis, "unknown_strategy")
        assert decision.direction == "HOLD"
        assert "Unknown strategy" in decision.rationale

    def test_all_strategies(self) -> None:
        """All supported strategies produce valid decisions."""
        engine = ReasoningEngine()
        for strategy in ("trend_following", "mean_reversion", "momentum", "breakout"):
            analysis = Analysis(trend="bullish", strength=0.5)
            decision = engine._decide(analysis, strategy)
            assert decision.direction in ("BUY", "SELL", "HOLD")


# ---------------------------------------------------------------------------
# Justify step
# ---------------------------------------------------------------------------


class TestJustify:
    """Tests for the _justify step."""

    def test_justify_buy(self) -> None:
        """Justification for BUY decision."""
        engine = ReasoningEngine()
        decision = Decision(direction="BUY", confidence=0.8, rationale="Trend up")
        analysis = Analysis(trend="bullish", strength=0.5, indicators={"rsi": "55"})
        text = engine._justify(decision, analysis)
        assert "BUY" in text
        assert "bullish" in text
        assert "Trend up" in text
        assert "rsi" in text

    def test_justify_sell(self) -> None:
        """Justification for SELL decision."""
        engine = ReasoningEngine()
        decision = Decision(direction="SELL", confidence=0.7, rationale="Trend down")
        analysis = Analysis(trend="bearish", strength=-0.5)
        text = engine._justify(decision, analysis)
        assert "SELL" in text
        assert "bearish" in text

    def test_justify_hold(self) -> None:
        """Justification for HOLD decision."""
        engine = ReasoningEngine()
        decision = Decision(direction="HOLD", confidence=0.1)
        analysis = Analysis(trend="neutral", strength=0.0)
        text = engine._justify(decision, analysis)
        assert "HOLD" in text


# ---------------------------------------------------------------------------
# Full chain (async analyze)
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for the full async analyze method."""

    @pytest.mark.asyncio
    async def test_analyze_bullish(self, sample_features: dict[str, float]) -> None:
        """Full analysis with bullish features."""
        engine = ReasoningEngine()
        chain = await engine.analyze(sample_features, "trend_following")
        assert isinstance(chain, ReasoningChain)
        assert chain.decision.direction in ("BUY", "SELL", "HOLD")
        assert 0.0 <= chain.confidence <= 1.0
        assert len(chain.justification) > 0

    @pytest.mark.asyncio
    async def test_analyze_bearish(self, sample_bearish_features: dict[str, float]) -> None:
        """Full analysis with bearish features."""
        engine = ReasoningEngine()
        chain = await engine.analyze(sample_bearish_features, "trend_following")
        assert chain.decision.direction in ("BUY", "SELL", "HOLD")
        assert chain.observation.features
        assert chain.analysis.indicators

    @pytest.mark.asyncio
    async def test_analyze_each_strategy(self, sample_features: dict[str, float]) -> None:
        """Analysis works for all strategies."""
        engine = ReasoningEngine()
        for strategy in ("trend_following", "mean_reversion", "momentum", "breakout"):
            chain = await engine.analyze(sample_features, strategy)
            assert chain.decision.direction in ("BUY", "SELL", "HOLD")
            assert chain.confidence >= 0.0

    @pytest.mark.asyncio
    async def test_analyze_with_none_features(self) -> None:
        """Analysis handles None features gracefully."""
        engine = ReasoningEngine()
        features = {"rsi_14": 55.0, "macd": None, "close": 100.0}
        chain = await engine.analyze(features, "trend_following")
        assert chain.decision.direction in ("BUY", "SELL", "HOLD")

    @pytest.mark.asyncio
    async def test_analyze_empty_features(self) -> None:
        """Analysis with empty features → HOLD with low confidence."""
        engine = ReasoningEngine()
        chain = await engine.analyze({}, "trend_following")
        assert chain.decision.direction == "HOLD"
        assert chain.confidence < 0.2

    @pytest.mark.asyncio
    async def test_analyze_all_none_features(self) -> None:
        """Analysis with all None features → HOLD."""
        engine = ReasoningEngine()
        features = {f: None for f in ["rsi_14", "macd", "ema_9", "close"]}
        chain = await engine.analyze(features, "trend_following")
        assert chain.decision.direction == "HOLD"

    @pytest.mark.asyncio
    async def test_confidence_range(self, sample_features: dict[str, float]) -> None:
        """Confidence is always in [0, 1]."""
        engine = ReasoningEngine()
        for strategy in ("trend_following", "mean_reversion", "momentum", "breakout"):
            chain = await engine.analyze(sample_features, strategy)
            assert 0.0 <= chain.confidence <= 1.0, f"Confidence {chain.confidence} out of range for {strategy}"

    @pytest.mark.asyncio
    async def test_observation_populated(self, sample_features: dict[str, float]) -> None:
        """Observation contains available features."""
        engine = ReasoningEngine()
        chain = await engine.analyze(sample_features, "trend_following")
        assert len(chain.observation.features) > 0
        assert "summary" in chain.observation.summary.lower() or "Available" in chain.observation.summary

    @pytest.mark.asyncio
    async def test_analysis_has_indicators(self, sample_features: dict[str, float]) -> None:
        """Analysis contains interpreted indicators."""
        engine = ReasoningEngine()
        chain = await engine.analyze(sample_features, "trend_following")
        assert len(chain.analysis.indicators) > 0
        assert chain.analysis.trend in ("bullish", "bearish", "neutral")

    @pytest.mark.asyncio
    async def test_justification_is_text(self, sample_features: dict[str, float]) -> None:
        """Justification is a non-empty string."""
        engine = ReasoningEngine()
        chain = await engine.analyze(sample_features, "trend_following")
        assert isinstance(chain.justification, str)
        assert len(chain.justification) > 10
