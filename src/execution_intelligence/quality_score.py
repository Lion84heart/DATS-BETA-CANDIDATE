"""Trade Quality Score (Phase 4, module 7).

A composite 0-100 score for a candidate entry, computed only from the
frozen strategies' own signals and the frozen Decision Fusion's own
output — never a new signal source. Consumed by the Entry Quality
Filter (module 1) and the Position Sizing Engine (module 6).

Three components:
  - Confidence (45%): the fused decision's own confidence.
  - Consensus (35%): fraction of the 8 strategies voting the same
    direction as the fused decision — a signal several strategies
    agree on is more likely durable than a narrow majority.
  - Volatility context (20%): how far current ATR sits from its own
    trailing average. Sprint 7's loss-attribution research found
    volatility spikes present in 40% of losing trades — this penalizes
    entries during unusually elevated (or unusually depressed, which
    is also a regime change) volatility relative to what's typical for
    that symbol recently, rather than a fixed absolute threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from intelligence.fusion import FusedDecision
from trading.schemas import StrategySignal

_CONFIDENCE_WEIGHT = 0.45
_CONSENSUS_WEIGHT = 0.35
_VOLATILITY_WEIGHT = 0.20


@dataclass
class QualityScoreBreakdown:
    score: float  # 0-100
    confidence_component: float
    consensus_component: float
    volatility_component: float
    vote_consensus_frac: float
    atr_ratio: float | None  # current ATR / trailing average ATR; None if not yet available


def compute_trade_quality_score(
    signals: list[StrategySignal],
    fused: FusedDecision,
    current_atr: float | None,
    trailing_avg_atr: float | None,
) -> QualityScoreBreakdown:
    n = len(signals)
    agreeing = sum(1 for s in signals if s.direction == fused.direction)
    consensus_frac = agreeing / n if n else 0.0

    confidence_component = fused.confidence * 100.0
    consensus_component = consensus_frac * 100.0

    atr_ratio: float | None = None
    if current_atr is not None and trailing_avg_atr and trailing_avg_atr > 0:
        atr_ratio = current_atr / trailing_avg_atr
        deviation = abs(atr_ratio - 1.0)
        volatility_component = max(0.0, 100.0 - deviation * 100.0)
    else:
        volatility_component = 50.0  # neutral when there's not yet enough history for ATR context

    score = (
        _CONFIDENCE_WEIGHT * confidence_component
        + _CONSENSUS_WEIGHT * consensus_component
        + _VOLATILITY_WEIGHT * volatility_component
    )
    return QualityScoreBreakdown(
        score=round(score, 2),
        confidence_component=round(confidence_component, 2),
        consensus_component=round(consensus_component, 2),
        volatility_component=round(volatility_component, 2),
        vote_consensus_frac=round(consensus_frac, 4),
        atr_ratio=round(atr_ratio, 4) if atr_ratio is not None else None,
    )
