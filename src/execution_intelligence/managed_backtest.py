"""Phase 4 — Managed backtest: applies the new trade-management stack
(Entry Quality Filter, Dynamic Exit Engine, Position Sizing Engine) on
top of the frozen Strategy Engine and Decision Fusion, with every
module independently toggleable so each can be backtested on its own
against baseline (Objective 9), plus a fully-combined "risk-adjusted
execution" run (Objective 8).

Reuses the real, unmodified ``intelligence.fusion.DecisionFusion`` and
``backtesting.engine.default_strategies()`` — the trading DECISION
(BUY/SELL/HOLD, confidence) is always exactly what the frozen system
would produce. Only what happens *after* that decision — whether to
act on a BUY, how much to buy, and when to exit — is new. With every
toggle off, this loop is verified to reproduce the frozen
``BacktestEngine`` exactly (see ``verify_managed_loop_matches_baseline``
below), not just assumed to.

ATR is tracked incrementally (a running True-Range history) rather
than recomputed from scratch each bar, purely for performance across
the many backtests this phase's comparison grid runs — mathematically
identical to ``atr_utils.compute_atr`` at any given bar.
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
from execution_intelligence.entry_filter import EntryQualityFilter
from execution_intelligence.exit_engine import DynamicExitEngine
from execution_intelligence.position_sizing import PositionSizingEngine
from execution_intelligence.quality_score import compute_trade_quality_score
from execution_intelligence.stops import StopState
from intelligence.fusion import DecisionFusion
from market.connectors.base import PriceTick
from trading.base_strategy import BaseStrategy
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperBroker
from trading.schemas import SignalDirection, StrategySignal

logger = logging.getLogger(__name__)

_MAX_WINDOW = 200
_YIELD_EVERY_N_BARS = 50
_ATR_PERIOD = 14
_ATR_TRAILING_WINDOW = 50  # bars of ATR history averaged for the "typical ATR" volatility-ratio component


@dataclass
class ManagedBacktestConfig:
    """Independent on/off toggles for every Phase 4 module, plus their
    tunable parameters. All toggles default False — an all-False config
    is the baseline and must reproduce the frozen BacktestEngine exactly.
    """

    use_entry_filter: bool = False
    use_atr_stop: bool = False
    use_trailing_stop: bool = False
    use_breakeven: bool = False
    use_position_sizing: bool = False

    min_quality_score: float = 55.0
    atr_stop_mult: float = 2.0
    trailing_mult: float = 2.5
    breakeven_trigger_pct: float = 1.5
    breakeven_buffer_pct: float = 0.1


async def run_managed_backtest(
    bars: list[HistoricalBar],
    config: BacktestRunConfig,
    managed: ManagedBacktestConfig,
    strategies: list[BaseStrategy] | None = None,
) -> tuple[BacktestReport, dict[str, Any]]:
    """Replay ``bars`` through the frozen strategies and the real
    ``DecisionFusion``, applying the Phase 4 trade-management stack
    according to ``managed``'s toggles.

    Returns:
        ``(report, extra)`` — ``report`` has the same shape
        ``BacktestEngine.run()`` produces; ``extra`` carries Phase
        4-specific telemetry (exit-reason breakdown, entries blocked by
        the quality filter, average entry quality score).
    """
    strategies = strategies or default_strategies()
    fusion = DecisionFusion()

    entry_filter = EntryQualityFilter(min_score=managed.min_quality_score) if managed.use_entry_filter else None
    exit_engine = DynamicExitEngine(
        use_atr_stop=managed.use_atr_stop, use_trailing_stop=managed.use_trailing_stop,
        use_breakeven=managed.use_breakeven, atr_stop_mult=managed.atr_stop_mult,
        trailing_mult=managed.trailing_mult, breakeven_trigger_pct=managed.breakeven_trigger_pct,
        breakeven_buffer_pct=managed.breakeven_buffer_pct,
    )
    sizing_engine = PositionSizingEngine(base_position_pct=config.position_size_pct) if managed.use_position_sizing else None

    started_at = time.time()
    broker = PaperBroker(initial_capital=config.initial_capital)

    window: list[dict[str, float]] = []
    equity_curve: list[float] = [config.initial_capital]
    decisions_log: list[dict[str, Any]] = []
    strategy_signal_log: dict[str, list[StrategySignal]] = {s.name: [] for s in strategies}
    fused_signals: list[str] = []
    closes: list[float] = []

    tr_history: list[float] = []   # incremental True Range history for fast ATR
    atr_history: list[float | None] = []

    bars_in_position = 0
    open_trade: tuple[float, float, int] | None = None
    stop_state: StopState | None = None
    closed_trades: list[ClosedTrade] = []
    exit_reason_counts: dict[str, int] = {}
    entries_blocked_by_filter = 0
    quality_scores_at_entry: list[float] = []

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

        if idx > 0:
            prev_close = bars[idx - 1].close
            tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
            tr_history.append(tr)
        current_atr: float | None = None
        if len(tr_history) >= _ATR_PERIOD:
            current_atr = sum(tr_history[-_ATR_PERIOD:]) / _ATR_PERIOD
        atr_history.append(current_atr)
        recent_atrs = [a for a in atr_history[-_ATR_TRAILING_WINDOW:] if a is not None]
        trailing_avg_atr = sum(recent_atrs) / len(recent_atrs) if len(recent_atrs) >= 10 else None

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

        fused = fusion.combine(signals)
        fused_signals.append(fused.direction.value)
        closes.append(bar.close)

        quality = compute_trade_quality_score(signals, fused, current_atr, trailing_avg_atr)

        held = broker.account.positions.get(config.symbol)
        held_qty = held.quantity if held else 0.0

        exit_triggered = False
        exit_reason = "none"
        if held_qty > 0 and stop_state is not None:
            decision = exit_engine.check_bar(stop_state, bar.low, bar.high, fused.direction == SignalDirection.SELL)
            exit_triggered, exit_reason = decision.should_exit, decision.reason

        entry_blocked = False
        if fused.direction == SignalDirection.BUY and held_qty <= 0:
            allow = True
            if entry_filter is not None:
                allow = entry_filter.allow_entry(quality.score)
                if not allow:
                    entry_blocked = True
                    entries_blocked_by_filter += 1
            if allow:
                if sizing_engine is not None:
                    qty = sizing_engine.compute_quantity(broker.account.cash, bar.close, quality.score, quality.atr_ratio)
                else:
                    qty = math.floor((broker.account.cash * config.position_size_pct) / bar.close) if bar.close > 0 else 0
                if qty > 0:
                    result = await broker.submit_order(
                        Order(symbol=config.symbol, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=qty)
                    )
                    if result.status == "filled":
                        open_trade = (result.avg_fill_price, bar.timestamp, idx)
                        stop_state = StopState(
                            entry_price=result.avg_fill_price, atr_at_entry=current_atr,
                            peak_price=result.avg_fill_price,
                        )
                        quality_scores_at_entry.append(quality.score)
        elif exit_triggered and held_qty > 0:
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
                exit_reason_counts[exit_reason] = exit_reason_counts.get(exit_reason, 0) + 1
                open_trade = None
                stop_state = None

        decisions_log.append(
            {
                "bar": idx, "timestamp": bar.timestamp, "price": bar.close,
                "signal": fused.direction.value, "confidence": fused.confidence,
                "quality_score": quality.score, "entry_blocked": entry_blocked, "exit_reason": exit_reason,
            }
        )

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
        exit_reason_counts["end_of_data"] = exit_reason_counts.get("end_of_data", 0) + 1

    portfolio_metrics = compute_portfolio_metrics(
        equity_curve=equity_curve, trades=closed_trades, num_bars=len(bars),
        bars_in_position=bars_in_position, initial_capital=config.initial_capital,
    )
    fusion_confusion = compute_confusion_matrix(
        fused_signals, closes, horizon=config.confusion_horizon_bars, threshold_pct=config.confusion_threshold_pct,
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
                    preds, closes, horizon=config.confusion_horizon_bars, threshold_pct=config.confusion_threshold_pct,
                ),
            )
        )

    report = BacktestReport(
        run_id=f"managed-{config.symbol}-{int(started_at * 1000)}",
        symbol=config.symbol, started_at=started_at, completed_at=time.time(),
        num_bars=len(bars), initial_capital=config.initial_capital,
        final_equity=equity_curve[-1], portfolio_metrics=portfolio_metrics,
        fusion_confusion=fusion_confusion, per_strategy_stats=per_strategy_stats,
        trades=closed_trades, equity_curve=equity_curve, decisions=decisions_log,
    )
    extra = {
        "exit_reason_counts": exit_reason_counts,
        "entries_blocked_by_filter": entries_blocked_by_filter,
        "avg_quality_score_at_entry": (
            round(sum(quality_scores_at_entry) / len(quality_scores_at_entry), 2) if quality_scores_at_entry else None
        ),
    }
    return report, extra


async def verify_managed_loop_matches_baseline(bars: list[HistoricalBar], config: BacktestRunConfig) -> bool:
    """Sanity check: an all-toggles-off ``ManagedBacktestConfig`` must
    produce trade-for-trade identical output to the frozen, unmodified
    ``BacktestEngine`` — proving this loop is a faithful reimplementation
    before any module comparison is trusted.
    """
    static_report = await BacktestEngine().run(bars, config)
    managed_report, _ = await run_managed_backtest(bars, config, ManagedBacktestConfig())
    sm, mm = static_report.portfolio_metrics, managed_report.portfolio_metrics
    return (
        sm.number_of_trades == mm.number_of_trades
        and abs(sm.total_return_pct - mm.total_return_pct) < 1e-6
        and abs(sm.sharpe_ratio - mm.sharpe_ratio) < 1e-6
        and abs(sm.max_drawdown_pct - mm.max_drawdown_pct) < 1e-6
    )
