"""Confusion statistics for BUY/SELL/HOLD signals.

There's no external "ground truth" label for a trading signal — so
"actual" here is defined the standard way a signal is evaluated in
backtesting: what the price actually did over a forward-looking horizon
after the signal was issued, bucketed into UP / DOWN / FLAT by a minimum
percentage-change threshold. This gives a real, computable 3x3 confusion
matrix (predicted signal x actual subsequent move) from data already in
the backtest — not a fabricated evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_PREDICTED_LABELS = ("BUY", "SELL", "HOLD")
_ACTUAL_LABELS = ("UP", "DOWN", "FLAT")
_CORRECT_ACTUAL_FOR = {"BUY": "UP", "SELL": "DOWN", "HOLD": "FLAT"}


@dataclass
class ConfusionMatrix:
    """3x3 matrix of predicted signal vs. actual subsequent price move."""

    horizon_bars: int
    threshold_pct: float
    matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    precision_pct: dict[str, float] = field(default_factory=dict)
    support: dict[str, int] = field(default_factory=dict)  # bars evaluated per predicted class


def compute_confusion_matrix(
    predictions: list[str],
    closes: list[float],
    horizon: int = 5,
    threshold_pct: float = 0.1,
) -> ConfusionMatrix:
    """Build a confusion matrix of predicted signal vs. actual future move.

    Args:
        predictions: Signal issued at each bar (BUY/SELL/HOLD), aligned
            1:1 with ``closes``.
        closes: Close price at each bar.
        horizon: Bars ahead to look for the "actual" outcome.
        threshold_pct: Minimum |% change| over the horizon to count as
            UP/DOWN rather than FLAT.

    Returns:
        ConfusionMatrix with raw counts and per-predicted-class precision
        (the % of a signal's occurrences where the market actually moved
        the way that signal implied — UP for BUY, DOWN for SELL, FLAT
        for HOLD).
    """
    matrix: dict[str, dict[str, int]] = {p: {a: 0 for a in _ACTUAL_LABELS} for p in _PREDICTED_LABELS}

    n = len(predictions)
    for i in range(n):
        j = i + horizon
        if j >= len(closes):
            continue  # not enough forward data to evaluate this bar yet
        base = closes[i]
        if not base:
            continue
        change_pct = (closes[j] - base) / base * 100.0
        if change_pct > threshold_pct:
            actual = "UP"
        elif change_pct < -threshold_pct:
            actual = "DOWN"
        else:
            actual = "FLAT"

        predicted = predictions[i]
        if predicted in matrix:
            matrix[predicted][actual] += 1

    precision_pct: dict[str, float] = {}
    support: dict[str, int] = {}
    for predicted in _PREDICTED_LABELS:
        row = matrix[predicted]
        total = sum(row.values())
        support[predicted] = total
        correct = row[_CORRECT_ACTUAL_FOR[predicted]]
        precision_pct[predicted] = round(correct / total * 100.0, 2) if total else 0.0

    return ConfusionMatrix(
        horizon_bars=horizon,
        threshold_pct=threshold_pct,
        matrix=matrix,
        precision_pct=precision_pct,
        support=support,
    )
