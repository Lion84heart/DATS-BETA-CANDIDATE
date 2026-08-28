"""DATS Continuous Learning & Decision Intelligence Framework.

Records trading decisions with full context for post-trade analysis,
continuous improvement, and external AI review.
"""

from __future__ import annotations

from .decisions import DecisionRecord, DecisionPackage, DecisionStore
from .evaluation import PostTradeEvaluator, OutcomeLabel

__all__ = [
    "DecisionRecord",
    "DecisionPackage",
    "DecisionStore",
    "PostTradeEvaluator",
    "OutcomeLabel",
]
