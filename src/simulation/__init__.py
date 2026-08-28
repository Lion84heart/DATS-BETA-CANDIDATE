"""DATS Trading Simulation Module (M9).

End-to-end trading simulation pipeline integrating strategies,
risk management, execution, monitoring, and decision intelligence.
"""

from __future__ import annotations

from .market_sim import MarketSimulator, PricePath
from .trading_loop import SimulationResult, TradingSimulator
from .performance import SimulationAnalyzer

__all__ = [
    "MarketSimulator",
    "PricePath",
    "TradingSimulator",
    "SimulationResult",
    "SimulationAnalyzer",
]
