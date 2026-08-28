"""DATS — Strategy Engine (Milestone M4).

The strategy engine provides:
- Abstract base strategy with hot-swap parameter support
- Five production strategies (trend, mean-reversion, momentum, breakout, stat-arb)
- Event-driven backtesting engine with transaction cost modeling
- Parameter optimization (grid search, random search, walk-forward)
- Hot-swap strategy registry
- Performance tracking and comparison
- A/B testing framework
"""

from trading.ab_testing import ABTestFramework
from trading.backtest import BacktestEngine
from trading.base_strategy import BaseStrategy
from trading.hotswap import StrategyRegistry
from trading.optimization import ParameterOptimizer
from trading.performance import PerformanceTracker
from trading.schemas import (
    ABTest,
    ABTestResult,
    BacktestResult,
    PerformanceMetrics,
    SignalDirection,
    StrategyConfig,
    StrategySignal,
    StrategyState,
    StrategyType,
    TradeRecord,
)

__all__ = [
    # Core
    "BaseStrategy",
    "BacktestEngine",
    "ParameterOptimizer",
    "StrategyRegistry",
    "PerformanceTracker",
    "ABTestFramework",
    # Schemas
    "ABTest",
    "ABTestResult",
    "BacktestResult",
    "PerformanceMetrics",
    "SignalDirection",
    "StrategyConfig",
    "StrategySignal",
    "StrategyState",
    "StrategyType",
    "TradeRecord",
]
