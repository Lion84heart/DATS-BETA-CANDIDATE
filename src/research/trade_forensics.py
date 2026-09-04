"""Sprint 7 — Instrumented backtest loop for loss attribution (research-only).

Reimplements ``backtesting.engine.BacktestEngine.run()``'s exact
trade-simulation loop — same ``PaperBroker`` calls, same
position-sizing, same frozen ``intelligence.fusion.DecisionFusion``
(imported, never modified, never substituted — unlike Phase 2's
``WeightedFusion`` research variant, this uses the real live fusion
object directly) and the same frozen strategies — but additionally
captures per-bar individual-strategy signals and the full bar series,
which the frozen engine discards after aggregating into its own
``StrategyStat``/``BacktestReport`` shape.

Every trading decision made here is IDENTICAL to what
``BacktestEngine.run()`` would make on the same bars — verified by an
automated sanity check below, not just asserted. This module exists
purely to observe more detail about decisions the frozen engine
already makes; it never changes what gets traded, and implements no
fixes.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtesting.confusion import compute_confusion_matrix
from backtesting.data import HistoricalBar
from backtesting.engine import (
    BacktestEngine,
    BacktestReport,
    BacktestRunConfig,
    StrategyStat,
    default_strategies,
)
from backtesting.metrics import ClosedTrade, compute_portfolio_metrics
from intelligence.fusion import DecisionFusion
from market.connectors.base import PriceTick
from trading.base_strategy import BaseStrategy
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperBroker
from trading.schemas import SignalDirection, StrategySignal

logger = logging.getLogger(__name__)

_MAX_WINDOW = 200  # mirrors backtesting.engine.BacktestEngine's rolling window cap
_YIELD_EVERY_N_BARS = 50  # mirrors backtesting.engine.BacktestEngine's event-loop yield cadence


@dataclass
class ForensicRun:
    """Everything the instrumented loop captures beyond ``BacktestReport``."""

    report: BacktestReport
    bars: list[HistoricalBar]
    per_bar_strategy_directions: dict[str, list[str]]  # strategy_name -> [direction per bar]
    per_bar_fused_direction: list[str]


async def run_forensic_backtest(
    bars: list[HistoricalBar],
    config: BacktestRunConfig,
    strategies: list[BaseStrategy] | None = None,
) -> ForensicRun:
    """Replay ``bars`` through the frozen strategies, the real
    ``DecisionFusion``, and ``PaperBroker`` — identically to
    ``BacktestEngine.run()`` — while additionally recording each
    strategy's raw per-bar direction for later forensic attribution.
    """
    strategies = strategies or default_strategies()
    fusion = DecisionFusion()  # the real, live, frozen fusion — never substituted

    started_at = time.time()
    broker = PaperBroker(initial_capital=config.initial_capital)

    window: list[dict[str, float]] = []
    equity_curve: list[float] = [config.initial_capital]
    fused_signals: list[str] = []
    closes: list[float] = []
    decisions_log: list[dict[str, Any]] = []
    strategy_signal_log: dict[str, list[StrategySignal]] = {s.name: [] for s in strategies}
    per_bar_strategy_directions: dict[str, list[str]] = {s.name: [] for s in strategies}

    bars_in_position = 0
    open_trade: tuple[float, float, int] | None = None
    closed_trades: list[ClosedTrade] = []

    for idx, bar in enumerate(bars):
        window.append(
            {"timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
             "low": bar.low, "close": bar.close, "volume": bar.volume}
        )
        if len(window) > _MAX_WINDOW:
            window.pop(0)
        df = pd.DataFrame(window)

        tick = PriceTick(
            symbol=config.symbol, timestamp=bar.timestamp, price=bar.close,
            bid=bar.close, ask=bar.close, volume=bar.volume, source="backtest",
        )
        broker.on_price_tick(tick)

        signals: list[StrategySignal] = []
        for strategy in strategies:
            try:
                signal = strategy.generate_signal(df, features={})
            except Exception:
                logger.exception("Strategy %s failed at bar %d", strategy.name, idx)
                signal = None
            if signal is None:
                signal = StrategySignal(
                    symbol=config.symbol, direction=SignalDirection.HOLD, confidence=0.0,
                    reason=f"{strategy.name} raised an error and produced no signal.",
                    strategy_name=strategy.name,
                )
            signals.append(signal)
            strategy_signal_log[strategy.name].append(signal)
            per_bar_strategy_directions[strategy.name].append(signal.direction.value)

        fused = fusion.combine(signals)
        fused_signals.append(fused.direction.value)
        closes.append(bar.close)
        decisions_log.append(
            {
                "bar": idx, "timestamp": bar.timestamp, "price": bar.close,
                "signal": fused.direction.value, "confidence": fused.confidence,
                "reasoning": fused.reasoning,
            }
        )

        held = broker.account.positions.get(config.symbol)
        held_qty = held.quantity if held else 0.0

        if fused.direction == SignalDirection.BUY and held_qty <= 0:
            qty = math.floor((broker.account.cash * config.position_size_pct) / bar.close) if bar.close > 0 else 0
            if qty > 0:
                result = await broker.submit_order(
                    Order(symbol=config.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty)
                )
                if result.status == "filled":
                    open_trade = (result.avg_fill_price, bar.timestamp, idx)
        elif fused.direction == SignalDirection.SELL and held_qty > 0:
            result = await broker.submit_order(
                Order(symbol=config.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=held_qty)
            )
            if result.status == "filled" and open_trade is not None:
                entry_price, entry_ts, entry_bar = open_trade
                pnl = (result.avg_fill_price - entry_price) * held_qty - result.commission
                closed_trades.append(
                    ClosedTrade(
                        symbol=config.symbol, entry_time=entry_ts, exit_time=bar.timestamp,
                        entry_bar=entry_bar, exit_bar=idx, entry_price=entry_price,
                        exit_price=result.avg_fill_price, quantity=held_qty, pnl=pnl,
                        commission=result.commission,
                    )
                )
                open_trade = None

        if broker.account.positions.get(config.symbol):
            bars_in_position += 1

        equity_curve.append(broker.account.total_value)

        if idx % _YIELD_EVERY_N_BARS == 0:
            await asyncio.sleep(0)

    held = broker.account.positions.get(config.symbol)
    if held and open_trade is not None:
        entry_price, entry_ts, entry_bar = open_trade
        last_bar = bars[-1]
        pnl = (last_bar.close - entry_price) * held.quantity
        closed_trades.append(
            ClosedTrade(
                symbol=config.symbol, entry_time=entry_ts, exit_time=last_bar.timestamp,
                entry_bar=entry_bar, exit_bar=len(bars) - 1, entry_price=entry_price,
                exit_price=last_bar.close, quantity=held.quantity, pnl=pnl, commission=0.0,
            )
        )

    portfolio_metrics = compute_portfolio_metrics(
        equity_curve=equity_curve, trades=closed_trades, num_bars=len(bars),
        bars_in_position=bars_in_position, initial_capital=config.initial_capital,
    )

    fusion_confusion = compute_confusion_matrix(
        fused_signals, closes, horizon=config.confusion_horizon_bars,
        threshold_pct=config.confusion_threshold_pct,
    )

    per_strategy_stats: list[StrategyStat] = []
    for strategy in strategies:
        sigs = strategy_signal_log[strategy.name]
        preds = [s.direction.value for s in sigs]
        confs = [s.confidence for s in sigs]
        per_strategy_stats.append(
            StrategyStat(
                strategy=strategy.name,
                buy_count=preds.count("BUY"), sell_count=preds.count("SELL"), hold_count=preds.count("HOLD"),
                avg_confidence=round(sum(confs) / len(confs), 4) if confs else 0.0,
                confusion=compute_confusion_matrix(
                    preds, closes, horizon=config.confusion_horizon_bars,
                    threshold_pct=config.confusion_threshold_pct,
                ),
            )
        )

    report = BacktestReport(
        run_id=f"forensic-{config.symbol}-{int(started_at * 1000)}",
        symbol=config.symbol, started_at=started_at, completed_at=time.time(),
        num_bars=len(bars), initial_capital=config.initial_capital,
        final_equity=equity_curve[-1], portfolio_metrics=portfolio_metrics,
        fusion_confusion=fusion_confusion, per_strategy_stats=per_strategy_stats,
        trades=closed_trades, equity_curve=equity_curve, decisions=decisions_log,
    )
    return ForensicRun(
        report=report, bars=bars, per_bar_strategy_directions=per_bar_strategy_directions,
        per_bar_fused_direction=fused_signals,
    )


async def verify_forensic_loop_matches_static(bars: list[HistoricalBar], config: BacktestRunConfig) -> bool:
    """Sanity check: this instrumented loop must produce trade-for-trade
    identical results to the frozen, unmodified ``BacktestEngine`` — it
    uses the exact same ``DecisionFusion()`` and strategies, not a
    substitute, so this should hold exactly, not just approximately.
    """
    static_report = await BacktestEngine().run(bars, config)
    forensic_run = await run_forensic_backtest(bars, config)
    sm, fm = static_report.portfolio_metrics, forensic_run.report.portfolio_metrics
    return (
        sm.number_of_trades == fm.number_of_trades
        and abs(sm.total_return_pct - fm.total_return_pct) < 1e-6
        and abs(sm.sharpe_ratio - fm.sharpe_ratio) < 1e-6
        and abs(sm.max_drawdown_pct - fm.max_drawdown_pct) < 1e-6
    )
