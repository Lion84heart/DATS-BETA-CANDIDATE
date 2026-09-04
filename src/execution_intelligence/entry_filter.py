"""Entry Quality Filter (Phase 4, module 1).

Gates a candidate BUY on its Trade Quality Score. Does not change what
the frozen strategies or Decision Fusion decide — a blocked BUY simply
isn't acted on this bar; Fusion is free to re-issue BUY (with a
possibly different, re-evaluated quality score) on any later bar.
"""

from __future__ import annotations

_DEFAULT_MIN_SCORE = 55.0


class EntryQualityFilter:
    def __init__(self, min_score: float = _DEFAULT_MIN_SCORE) -> None:
        self.min_score = min_score

    def allow_entry(self, quality_score: float) -> bool:
        return quality_score >= self.min_score
