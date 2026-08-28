"""DATS Portfolio & Risk Management Module (M5).

Provides position sizing, risk metrics, kill switch circuit breakers,
and portfolio-level tracking for the trading system.
"""

from __future__ import annotations

from .position_sizing import KellyCriterion, PositionSizer, VolatilitySizer
from .risk_metrics import RiskMetrics, VaRModel
from .kill_switch import KillSwitch, KillSwitchTrigger
from .portfolio import PortfolioTracker, ExposureLimit

__all__ = [
    "KellyCriterion",
    "PositionSizer",
    "VolatilitySizer",
    "RiskMetrics",
    "VaRModel",
    "KillSwitch",
    "KillSwitchTrigger",
    "PortfolioTracker",
    "ExposureLimit",
]
