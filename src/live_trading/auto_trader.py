"""Live Auto-Trader: Market Data → Strategy Engine → Decision Fusion →
Risk Management → Paper Trading → Portfolio Update.

Wires the frozen Strategy Engine (``backtesting.engine.default_strategies``,
unmodified) and the real, unmodified ``intelligence.fusion.DecisionFusion``
to Phase 4's already-built, not-yet-deployed risk-management stack
(``execution_intelligence``), and — for the first time anywhere in this
codebase — actually submits the resulting BUY/SELL decisions as real
paper orders through the shared ``PaperBroker``, instead of only
recording them as advisory (the existing ``AIDecisionEngine`` keeps
doing that, unchanged, alongside this).

Every parameter here is Phase 4's own untuned default — this module
observes how the existing engine behaves live; it does not tune or
optimize anything.

Never risks real money: the only broker this ever calls is the paper
broker, and the only market-data connector this pairs with
(``market.connectors.binance_live.BinanceLiveConnector``) is
structurally read-only public market data — there is no code path
here, or anywhere in this application, that can place a real order.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from backtesting.engine import default_strategies
from execution_intelligence.entry_filter import EntryQualityFilter
from execution_intelligence.exit_engine import DynamicExitEngine
from execution_intelligence.position_sizing import PositionSizingEngine
from execution_intelligence.quality_score import compute_trade_quality_score
from execution_intelligence.stops import StopState, initial_atr_stop_price, take_profit_price
from intelligence.fusion import DecisionFusion
from market.connectors.base import PriceTick
from trading.base_strategy import BaseStrategy
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperBroker
from trading.schemas import SignalDirection, StrategySignal

from live_trading.trade_log import LiveTradeStore

logger = logging.getLogger(__name__)

_MAX_BARS_PER_SYMBOL = 200
_ATR_PERIOD = 14
_ATR_TRAILING_WINDOW = 50
_POSITION_SIZE_PCT = 0.95  # Phase 4's own default, untuned


@dataclass
class _SymbolState:
    bars: deque = field(default_factory=lambda: deque(maxlen=_MAX_BARS_PER_SYMBOL))
    prev_close: float | None = None
    tr_history: list[float] = field(default_factory=list)
    atr_history: list[float | None] = field(default_factory=list)
    stop_state: StopState | None = None
    open_trade_id: str | None = None
    take_profit: float | None = None
    processing: bool = False


class LiveAutoTrader:
    """Runs the full pipeline on every incoming live price tick."""

    def __init__(
        self,
        broker: PaperBroker,
        trade_store: LiveTradeStore | None = None,
        strategies: list[BaseStrategy] | None = None,
        fusion: DecisionFusion | None = None,
    ) -> None:
        self.broker = broker
        self.trade_store = trade_store or LiveTradeStore()
        self.strategies = strategies or default_strategies()
        self.fusion = fusion or DecisionFusion()

        # Phase 4's own default parameters, applied as-is — untuned.
        self.entry_filter = EntryQualityFilter(min_score=55.0)
        self.exit_engine = DynamicExitEngine(
            use_atr_stop=True, use_trailing_stop=True, use_breakeven=True, use_take_profit=True,
        )
        self.sizing_engine = PositionSizingEngine(base_position_pct=_POSITION_SIZE_PCT)

        self._symbols: dict[str, _SymbolState] = {}
        self._decisions_made = 0
        self._trades_opened = 0
        self._trades_closed = 0
        self._entries_blocked = 0

    def on_price_tick(self, tick: PriceTick) -> None:
        """Feed callback — synchronous, per the connector contract.
        Schedules the actual (async) analysis/execution as a background
        task on the running event loop so it never blocks the feed.
        """
        state = self._symbols.setdefault(tick.symbol, _SymbolState())
        if state.processing:
            return  # a previous tick's analysis for this symbol is still running — skip, don't queue up
        asyncio.create_task(self._safe_process(tick, state))

    async def _safe_process(self, tick: PriceTick, state: _SymbolState) -> None:
        state.processing = True
        try:
            await self._process(tick, state)
        except Exception:
            logger.exception("LiveAutoTrader failed processing tick for %s", tick.symbol)
        finally:
            state.processing = False

    async def _process(self, tick: PriceTick, state: _SymbolState) -> None:
        # Tick-as-bar: the same honest simplification already documented
        # and used throughout this codebase for tick-derived data (no
        # real intrabar range is available from a single price tick).
        state.bars.append(
            {"timestamp": tick.timestamp, "open": tick.price, "high": tick.price,
             "low": tick.price, "close": tick.price, "volume": tick.volume}
        )
        self._update_atr(tick, state)
        df = pd.DataFrame(list(state.bars))

        signals: list[StrategySignal] = []
        for strategy in self.strategies:
            try:
                signal = strategy.generate_signal(df, features={})
            except Exception:
                logger.exception("Strategy %s failed analyzing %s", strategy.name, tick.symbol)
                signal = None
            if signal is None:
                signal = StrategySignal(
                    symbol=tick.symbol, direction=SignalDirection.HOLD, confidence=0.0,
                    reason=f"{strategy.name} raised an error and produced no signal.",
                    strategy_name=strategy.name,
                )
            signals.append(signal)

        fused = self.fusion.combine(signals)
        self._decisions_made += 1
        current_atr = state.atr_history[-1] if state.atr_history else None
        recent = [a for a in state.atr_history[-_ATR_TRAILING_WINDOW:] if a is not None]
        trailing_avg_atr = sum(recent) / len(recent) if len(recent) >= 10 else None
        quality = compute_trade_quality_score(signals, fused, current_atr, trailing_avg_atr)

        votes = [
            {"strategy": s.strategy_name, "direction": s.direction.value, "confidence": s.confidence, "reason": s.reason}
            for s in signals
        ]

        held = self.broker.account.positions.get(tick.symbol)
        held_qty = held.quantity if held else 0.0

        if held_qty > 0 and state.stop_state is not None:
            await self._maybe_exit(tick, state, fused, votes, held_qty)
        elif fused.direction == SignalDirection.BUY and held_qty <= 0:
            await self._maybe_enter(tick, state, fused, quality, votes, current_atr)

        self._record_equity_snapshot()

    def _update_atr(self, tick: PriceTick, state: _SymbolState) -> None:
        if state.prev_close is not None:
            tr = abs(tick.price - state.prev_close)  # high=low=close=price -> true range reduces to |Δclose|
            state.tr_history.append(tr)
        state.prev_close = tick.price
        current_atr = None
        if len(state.tr_history) >= _ATR_PERIOD:
            current_atr = sum(state.tr_history[-_ATR_PERIOD:]) / _ATR_PERIOD
        state.atr_history.append(current_atr)

    async def _maybe_enter(
        self, tick: PriceTick, state: _SymbolState, fused, quality, votes: list[dict[str, Any]],
        current_atr: float | None,
    ) -> None:
        if not self.entry_filter.allow_entry(quality.score):
            self._entries_blocked += 1
            return

        qty = self.sizing_engine.compute_quantity(self.broker.account.cash, tick.price, quality.score, quality.atr_ratio)
        if qty <= 0:
            return

        result = await self.broker.submit_order(
            Order(symbol=tick.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty)
        )
        if result.status != "filled":
            return

        stop_loss = initial_atr_stop_price(result.avg_fill_price, current_atr, self.exit_engine.atr_stop_mult)
        take_profit = take_profit_price(result.avg_fill_price, current_atr, self.exit_engine.take_profit_mult)
        state.stop_state = StopState(entry_price=result.avg_fill_price, atr_at_entry=current_atr, peak_price=result.avg_fill_price)
        state.take_profit = take_profit

        state.open_trade_id = self.trade_store.open_trade(
            symbol=tick.symbol, entry_price=result.avg_fill_price, quantity=qty,
            stop_loss_price=stop_loss, take_profit_price=take_profit,
            entry_confidence=fused.confidence, entry_reasoning=fused.reasoning, entry_votes=votes,
        )
        self._trades_opened += 1
        logger.info(
            "LIVE PAPER BUY %s qty=%.6f @ %.4f (stop=%s, target=%s, confidence=%.2f)",
            tick.symbol, qty, result.avg_fill_price, stop_loss, take_profit, fused.confidence,
        )

    async def _maybe_exit(
        self, tick: PriceTick, state: _SymbolState, fused, votes: list[dict[str, Any]], held_qty: float,
    ) -> None:
        decision = self.exit_engine.check_bar(
            state.stop_state, bar_low=tick.price, bar_high=tick.price,
            fused_sell=(fused.direction == SignalDirection.SELL),
        )
        if not decision.should_exit:
            return

        result = await self.broker.submit_order(
            Order(symbol=tick.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=held_qty)
        )
        if result.status != "filled":
            return

        if state.open_trade_id is not None:
            self.trade_store.close_trade(
                trade_id=state.open_trade_id, exit_price=result.avg_fill_price, fees=result.commission,
                exit_reason=decision.reason, exit_confidence=fused.confidence,
                exit_reasoning=fused.reasoning, exit_votes=votes,
            )
        self._trades_closed += 1
        logger.info(
            "LIVE PAPER SELL %s qty=%.6f @ %.4f (reason=%s)",
            tick.symbol, held_qty, result.avg_fill_price, decision.reason,
        )
        state.stop_state = None
        state.open_trade_id = None
        state.take_profit = None

    def _record_equity_snapshot(self) -> None:
        try:
            self.trade_store.record_equity_snapshot(
                equity=self.broker.account.total_value, cash=self.broker.account.cash,
                open_position_count=len(self.broker.account.positions),
            )
        except Exception:
            logger.exception("Failed to record equity snapshot")

    def summary(self) -> dict[str, Any]:
        return {
            "decisions_made": self._decisions_made,
            "trades_opened": self._trades_opened,
            "trades_closed": self._trades_closed,
            "entries_blocked_by_filter": self._entries_blocked,
            "symbols_tracked": list(self._symbols.keys()),
            "open_positions": {
                sym: {"trade_id": s.open_trade_id, "stop_loss": s.stop_state.entry_price if s.stop_state else None,
                      "take_profit": s.take_profit}
                for sym, s in self._symbols.items() if s.open_trade_id is not None
            },
        }
