"""DATS — Trading Strategies.

Registers all production trading strategies for discovery and hot-swap deployment.
"""

from __future__ import annotations

from trading.strategies.breakout import BreakoutStrategy
from trading.strategies.mean_reversion import MeanReversionStrategy
from trading.strategies.momentum import MomentumStrategy
from trading.strategies.stat_arb import StatArbStrategy
from trading.strategies.trend_following import TrendFollowingStrategy

__all__ = [
    "BreakoutStrategy",
    "MeanReversionStrategy",
    "MomentumStrategy",
    "StatArbStrategy",
    "TrendFollowingStrategy",
]

# Strategy registry for discovery
STRATEGY_REGISTRY: dict[str, type] = {
    "trend_following": TrendFollowingStrategy,
    "mean_reversion": MeanReversionStrategy,
    "momentum": MomentumStrategy,
    "breakout": BreakoutStrategy,
    "stat_arb": StatArbStrategy,
}


def get_strategy_class(name: str) -> type | None:
    """Get a strategy class by name.

    Args:
        name: Strategy name (e.g. 'trend_following').

    Returns:
        The strategy class, or None if not found.
    """
    return STRATEGY_REGISTRY.get(name)


def list_strategy_names() -> list[str]:
    """List all registered strategy names."""
    return sorted(STRATEGY_REGISTRY.keys())
