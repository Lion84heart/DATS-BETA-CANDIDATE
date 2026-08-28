"""DATS Execution Pipeline Module (M6).

Provides order management, execution strategies, slippage modeling,
fill simulation, and order lifecycle tracking.
"""

from __future__ import annotations

from .orders import Order, OrderSide, OrderStatus, OrderType
from .order_lifecycle import OrderLifecycleManager
from .execution_engine import ExecutionEngine
from .execution_strategies import IcebergStrategy, TWAPStrategy, VWAPStrategy
from .slippage import FixedSlippage, SlippageModel, VolatilitySlippage
from .fills import FillSimulator

__all__ = [
    "Order",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "OrderLifecycleManager",
    "ExecutionEngine",
    "TWAPStrategy",
    "VWAPStrategy",
    "IcebergStrategy",
    "SlippageModel",
    "FixedSlippage",
    "VolatilitySlippage",
    "FillSimulator",
]
