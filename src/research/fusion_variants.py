"""Research-only fusion variants for comparison against live DecisionFusion.

These exist purely to generate comparative backtest evidence for Sprint
6's quantitative research. Neither class is imported by, or reachable
from, any live code path — the live AI Decision Engine
(intelligence/engine.py) continues to use intelligence.fusion.DecisionFusion
exclusively, unmodified.

Both classes return the same FusedDecision type intelligence.fusion
already defines, so they drop into backtesting.BacktestEngine's existing
``fusion=`` constructor parameter without any change to that (frozen)
engine.
"""

from __future__ import annotations

from collections import Counter

from intelligence.fusion import FusedDecision
from trading.schemas import SignalDirection, StrategySignal

# Deterministic tie-break order when majority voting produces a tie.
_TIE_BREAK_ORDER = (SignalDirection.HOLD, SignalDirection.BUY, SignalDirection.SELL)


class MajorityVoteFusion:
    """Simple unweighted majority vote — one strategy, one vote.

    Unlike the live DecisionFusion (confidence-weighted), every
    strategy's vote counts equally regardless of its stated confidence.
    Used as the "majority voting" baseline for objective 5's comparison.
    """

    def combine(self, signals: list[StrategySignal]) -> FusedDecision:
        if not signals:
            return FusedDecision(direction=SignalDirection.HOLD, confidence=0.0, reasoning="No signals — holding.")

        counts = Counter(s.direction for s in signals)
        max_votes = max(counts.values())
        leaders = [d for d, c in counts.items() if c == max_votes]
        winner = leaders[0] if len(leaders) == 1 else next(d for d in _TIE_BREAK_ORDER if d in leaders)

        n = len(signals)
        confidence = round(max_votes / n, 2)
        by_direction: dict[SignalDirection, list[StrategySignal]] = {}
        for s in signals:
            by_direction.setdefault(s.direction, []).append(s)
        parts = []
        for direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD):
            names = [s.strategy_name for s in by_direction.get(direction, [])]
            if names:
                parts.append(f"{direction.value} {len(names)}/{n}: {', '.join(names)}")
        reasoning = f"Majority vote: {winner.value} ({max_votes}/{n} strategies). " + "; ".join(parts)

        votes = {s.strategy_name: s.direction.value for s in signals}
        return FusedDecision(direction=winner, confidence=confidence, reasoning=reasoning, votes=votes)


class WeightedFusion:
    """Confidence-weighted vote with an additional per-strategy weight
    multiplier — generalizes the live DecisionFusion's algorithm.

    With every weight set to 1.0, this produces mathematically identical
    output to intelligence.fusion.DecisionFusion (verified in the Sprint
    6 research runner as a sanity check). With non-uniform weights, it
    lets a strategy's vote count for more or less than its own stated
    confidence alone would — used to backtest the weights this sprint's
    research recommends (objective 4/5), without ever touching the live
    fusion module.
    """

    _MIN_VOTE_WEIGHT = 0.05

    def __init__(self, weights: dict[str, float]):
        """Args:
            weights: strategy_name -> multiplier (1.0 = neutral, matches
                live DecisionFusion's behavior).
        """
        self.weights = weights

    def combine(self, signals: list[StrategySignal]) -> FusedDecision:
        if not signals:
            return FusedDecision(direction=SignalDirection.HOLD, confidence=0.0, reasoning="No signals — holding.")

        weight_totals: dict[SignalDirection, float] = {
            SignalDirection.BUY: 0.0, SignalDirection.SELL: 0.0, SignalDirection.HOLD: 0.0,
        }
        by_direction: dict[SignalDirection, list[StrategySignal]] = {}
        for s in signals:
            strategy_weight = self.weights.get(s.strategy_name, 1.0)
            vote_weight = max(s.confidence, self._MIN_VOTE_WEIGHT) * strategy_weight
            weight_totals[s.direction] += vote_weight
            by_direction.setdefault(s.direction, []).append(s)

        total = sum(weight_totals.values()) or 1.0
        winner = max(weight_totals, key=lambda d: weight_totals[d])
        confidence = round(min(1.0, weight_totals[winner] / total), 2)

        n = len(signals)
        parts = []
        for direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD):
            names = [s.strategy_name for s in by_direction.get(direction, [])]
            if names:
                avg_conf = sum(s.confidence for s in by_direction[direction]) / len(names)
                parts.append(f"{direction.value} {len(names)}/{n} (avg {avg_conf * 100:.0f}%): {', '.join(names)}")
        reasoning = (
            f"Weighted fusion: {winner.value} ({confidence * 100:.0f}% weighted agreement, "
            f"per-strategy weights applied). " + "; ".join(parts)
        )

        votes = {s.strategy_name: s.direction.value for s in signals}
        return FusedDecision(direction=winner, confidence=confidence, reasoning=reasoning, votes=votes)
