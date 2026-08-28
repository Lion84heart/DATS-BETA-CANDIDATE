"""Paper trading mode orchestrator.

Integrates market data, strategy, risk, execution, and decision
recording for complete end-to-end paper trading without real
capital at risk.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from market.connectors.base import PriceTick
from market.connectors.simulated import SimulatedConnector
from market.feed import FeedManager
from system.decision_pipeline import DecisionPipeline, PipelineContext
from trading.execution.paper_broker import PaperBroker
from trading.execution.orders import Order, OrderSide, OrderType


@dataclass
class PaperTradingConfig:
    """Configuration for paper trading mode."""

    symbols: list[str] = field(default_factory=list)
    strategy_fn: Callable[[list[float]], str] | None = None
    risk_fn: Callable[[dict], bool] | None = None
    position_size_fn: Callable[[float, float], float] | None = None
    initial_capital: float = 100000.0
    tick_interval: float = 1.0
    lookback: int = 20


class PaperTradingMode:
    """Paper trading mode — complete end-to-end without real capital.

    Orchestrates: market data → strategy → risk → position sizing →
    paper broker execution → decision recording.
    """

    def __init__(
        self,
        config: PaperTradingConfig,
        feed: FeedManager | None = None,
        broker: PaperBroker | None = None,
        pipeline: DecisionPipeline | None = None,
    ):
        """Initialize paper trading mode.

        Args:
            config: Paper trading configuration.
            feed: Feed manager (creates simulated if None).
            broker: Paper broker (creates default if None).
            pipeline: Decision recording pipeline (optional).
        """
        self.config = config
        self.feed = feed or FeedManager()
        self.broker = broker or PaperBroker(
            initial_capital=config.initial_capital,
        )
        self.pipeline = pipeline

        # Price history per symbol
        self._price_history: dict[str, list[float]] = {}
        self._running = False
        self._task: asyncio.Task | None = None

        # Connect broker to feed
        self._setup_feed()

    def _setup_feed(self) -> None:
        """Connect paper broker to feed for price updates."""
        if self.broker:
            self.feed.add_callback(self.broker.on_price_tick)

    async def start(self) -> bool:
        """Start paper trading mode.

        Returns:
            True if started successfully.
        """
        # Create and register simulated connector if not already done
        if not self.feed._connectors:
            sim = SimulatedConnector(
                seed=42,
                tick_interval=self.config.tick_interval,
            )
            for symbol in self.config.symbols:
                sim.configure_symbol(symbol, 100.0)
            self.feed.register_connector(sim, primary=True)

        ok = await self.feed.connect()
        if not ok:
            return False

        await self.feed.subscribe(self.config.symbols)
        await self.broker.connect()

        self._running = True
        self._task = asyncio.create_task(self._trading_loop())
        return True

    async def stop(self) -> None:
        """Stop paper trading mode."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        await self.broker.disconnect()
        await self.feed.disconnect()

    async def _trading_loop(self) -> None:
        """Main trading loop: process ticks, generate signals, execute."""
        async for tick in self.feed.stream():
            if not self._running:
                break

            symbol = tick.symbol
            price = tick.price

            # Update price history
            if symbol not in self._price_history:
                self._price_history[symbol] = []
            self._price_history[symbol].append(price)

            # Need enough history for strategy
            if len(self._price_history[symbol]) < self.config.lookback:
                continue

            # Trim history
            if len(self._price_history[symbol]) > self.config.lookback * 2:
                self._price_history[symbol] = self._price_history[symbol][-self.config.lookback * 2:]

            # Strategy signal
            if self.config.strategy_fn:
                signal = self.config.strategy_fn(self._price_history[symbol])

                # Risk check
                risk_context = {
                    "symbol": symbol,
                    "price": price,
                    "max_drawdown": 0.0,  # Simplified
                }
                if self.config.risk_fn and not self.config.risk_fn(risk_context):
                    continue

                # Position sizing
                if self.config.position_size_fn:
                    qty = self.config.position_size_fn(price, self.broker.account.cash)
                else:
                    qty = 1.0

                # Execute
                if signal == "BUY":
                    await self._execute_buy(symbol, price, qty, tick)
                elif signal == "SELL":
                    await self._execute_sell(symbol, price, qty, tick)

    async def _execute_buy(self, symbol: str, price: float, qty: float, tick: PriceTick) -> None:
        """Execute buy order."""
        order = Order(
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=qty,
            order_type=OrderType.MARKET,
        )
        result = await self.broker.submit_order(order)

        # Record decision
        if self.pipeline:
            context = PipelineContext(
                symbol=symbol,
                price=price,
                timestamp=time.time(),
                features={"price": price, "signal": 1.0},
                strategy_name="paper_strategy",
            )
            record = self.pipeline.record_decision(context, "Buy signal from paper strategy")

            # Update with execution
            from intelligence.decisions import DecisionExecutionResult
            exec_result = DecisionExecutionResult(
                order_id=result.order_id,
                filled_qty=result.filled_qty,
                avg_price=result.avg_fill_price,
                slippage_bps=result.slippage_bps,
                commission=result.commission,
                execution_time_ms=1.0,
                status=result.status,
            )
            self.pipeline.update_execution(record.decision_id, exec_result)

    async def _execute_sell(self, symbol: str, price: float, qty: float, tick: PriceTick) -> None:
        """Execute sell order."""
        order = Order(
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=qty,
            order_type=OrderType.MARKET,
        )
        result = await self.broker.submit_order(order)

        # Record decision
        if self.pipeline:
            context = PipelineContext(
                symbol=symbol,
                price=price,
                timestamp=time.time(),
                features={"price": price, "signal": -1.0},
                strategy_name="paper_strategy",
            )
            record = self.pipeline.record_decision(context, "Sell signal from paper strategy")

            from intelligence.decisions import DecisionExecutionResult
            exec_result = DecisionExecutionResult(
                order_id=result.order_id,
                filled_qty=result.filled_qty,
                avg_price=result.avg_fill_price,
                slippage_bps=result.slippage_bps,
                commission=result.commission,
                execution_time_ms=1.0,
                status=result.status,
            )
            self.pipeline.update_execution(record.decision_id, exec_result)

    def get_account_summary(self) -> dict[str, Any]:
        """Get paper trading account summary."""
        return {
            "cash": self.broker.account.cash,
            "total_value": self.broker.account.total_value,
            "total_pnl": self.broker.account.total_pnl,
            "total_return_pct": self.broker.account.total_return_pct,
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_entry": p.avg_entry_price,
                    "market_price": p.market_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                }
                for p in self.broker.account.positions.values()
            ],
            "symbols": self.config.symbols,
            "tick_count": sum(len(h) for h in self._price_history.values()),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize state."""
        return {
            "running": self._running,
            "config": {
                "symbols": self.config.symbols,
                "initial_capital": self.config.initial_capital,
                "tick_interval": self.config.tick_interval,
                "lookback": self.config.lookback,
            },
            "account": self.get_account_summary(),
            "broker": self.broker.to_dict(),
            "feed": {
                "connectors": list(self.feed._connectors.keys()),
                "state": self.feed.get_state().__dict__,
            },
        }
