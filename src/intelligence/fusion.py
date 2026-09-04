"""Decision Fusion.

Combines the independent BUY/SELL/HOLD signals from every strategy in
the Strategy Engine into a single final recommendation, via
confidence-weighted majority voting.

Deterministic and fully explainable — no LLM, no external AI API, no
machine-learning model. Every input is a rule-based technical-analysis
signal computed from real market data (see trading/strategies/), and
the combination rule itself is simple arithmetic over those inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from trading.schemas import SignalDirection, StrategySignal

# Every vote counts for at least this much, so a unanimous but low-
# confidence field of strategies (e.g. everyone at 0.1 confidence HOLD
# during warmup) can still produce a decisive fused HOLD rather than a
# degenerate 0-confidence tie.
_MIN_VOTE_WEIGHT = 0.05


@dataclass
class FusedDecision:
    """Result of combining multiple strategy signals into one decision."""

    direction: SignalDirection
    confidence: float
    reasoning: str
    votes: dict[str, str] = field(default_factory=dict)  # strategy_name -> signal


class DecisionFusion:
    """Confidence-weighted majority vote across all Strategy Engine outputs."""

    def combine(self, signals: list[StrategySignal]) -> FusedDecision:
        """Fuse a list of per-strategy signals into one final decision.

        Args:
            signals: One StrategySignal per strategy (BUY/SELL/HOLD each).

        Returns:
            FusedDecision with the winning direction, a confidence score
            derived from how much of the total weighted vote it won, and
            a human-readable breakdown of how each strategy voted.
        """
        if not signals:
            return FusedDecision(
                direction=SignalDirection.HOLD,
                confidence=0.0,
                reasoning="No strategy signals available — holding.",
            )

        weight: dict[SignalDirection, float] = {
            SignalDirection.BUY: 0.0,
            SignalDirection.SELL: 0.0,
            SignalDirection.HOLD: 0.0,
        }
        by_direction: dict[SignalDirection, list[StrategySignal]] = {
            SignalDirection.BUY: [],
            SignalDirection.SELL: [],
            SignalDirection.HOLD: [],
        }
        for signal in signals:
            vote_weight = max(signal.confidence, _MIN_VOTE_WEIGHT)
            weight[signal.direction] += vote_weight
            by_direction[signal.direction].append(signal)

        total_weight = sum(weight.values()) or 1.0
        winner = max(weight, key=lambda d: weight[d])
        confidence = round(min(1.0, weight[winner] / total_weight), 2)

        n = len(signals)
        parts: list[str] = []
        for direction in (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD):
            names = [s.strategy_name for s in by_direction[direction]]
            if not names:
                continue
            avg_conf = sum(s.confidence for s in by_direction[direction]) / len(names)
            parts.append(f"{direction.value} {len(names)}/{n} (avg {avg_conf * 100:.0f}%): {', '.join(names)}")

        reasoning = f"Fused decision: {winner.value} ({confidence * 100:.0f}% weighted agreement). " + "; ".join(parts)

        votes = {s.strategy_name: s.direction.value for s in signals}
        return FusedDecision(direction=winner, confidence=confidence, reasoning=reasoning, votes=votes)
