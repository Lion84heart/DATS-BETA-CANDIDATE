"""Phase 2 — Regime-aware backtest runner (research-only).

Mirrors ``backtesting.engine.BacktestEngine.run()``'s trade-simulation
loop exactly — same ``PaperBroker`` calls, same position-sizing, same
trade bookkeeping, same metrics/confusion computation via the frozen
``backtesting.metrics``/``backtesting.confusion`` modules — so a
regime-aware run is comparable to a frozen ``BacktestEngine`` run on
equal terms. The one deliberate difference: instead of one fixed
``DecisionFusion.combine()`` for the whole run, each bar's fusion call
uses the strategy-weight vector for *that bar's* detected regime, via
the Sprint 6 ``WeightedFusion`` generalization (already verified to
reproduce live ``DecisionFusion`` exactly at neutral weights).

``intelligence.fusion.DecisionFusion``, every strategy in
``trading/strategies/*``, ``trading/execution/paper_broker.py``, and
``backtesting.engine.BacktestEngine`` are never modified or subclassed
here — this module only orchestrates the same frozen pieces
differently. See ``verify_regime_loop_matches_static_at_neutral_weights``
below for a direct, automated check that this reimplementation is a
faithful match to the frozen engine's own semantics.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
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
from market.connectors.base import PriceTick
from research.fusion_variants import WeightedFusion
from research.regime import REGIMES, SIDEWAYS, detect_regimes, time_in_regime_pct
from trading.base_strategy import BaseStrategy
from trading.execution.orders import Order, OrderSide, OrderType
from trading.execution.paper_broker import PaperBroker
from trading.schemas import SignalDirection, StrategySignal

logger = logging.getLogger(__name__)

_MAX_WINDOW = 200  # mirrors backtesting.engine.BacktestEngine's rolling window cap
_YIELD_EVERY_N_BARS = 50  # mirrors backtesting.engine.BacktestEngine's event-loop yield cadence


async def run_regime_aware_backtest(
    bars: list[HistoricalBar],
    config: BacktestRunConfig,
    weights_by_regime: dict[str, dict[str, float]],
    strategies: list[BaseStrategy] | None = None,
) -> tuple[BacktestReport, dict[str, float]]:
    """Replay ``bars`` through the frozen strategies and ``PaperBroker``,
    fusing each bar's signals with the strategy-weight vector for that
    bar's detected regime instead of one fixed weighting for the run.

    Returns:
        (report, time_in_regime_pct) — report has the same shape
        ``BacktestEngine.run()`` produces, so it's directly comparable;
        each decision in ``report.decisions`` also carries its bar's
        ``regime`` label.
    """
    strategies = strategies or default_strategies()
    regimes = detect_regimes(bars)

    started_at = time.time()
    broker = PaperBroker(initial_capital=config.initial_capital)

    window: list[dict[str, float]] = []
    equity_curve: list[float] = [config.initial_capital]
    fused_signals: list[str] = []
    closes: list[float] = []
    decisions_log: list[dict[str, Any]] = []
    strategy_signal_log: dict[str, list[StrategySignal]] = {s.name: [] for s in strategies}

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

        regime = regimes[idx]
        weights = weights_by_regime.get(regime) or weights_by_regime.get(SIDEWAYS, {})
        fused = WeightedFusion(weights).combine(signals)

        fused_signals.append(fused.direction.value)
        closes.append(bar.close)
        decisions_log.append(
            {
                "bar": idx, "timestamp": bar.timestamp, "price": bar.close,
                "signal": fused.direction.value, "confidence": fused.confidence,
                "reasoning": fused.reasoning, "regime": regime,
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
        run_id=f"regime-bt-{config.symbol}-{int(started_at * 1000)}",
        symbol=config.symbol, started_at=started_at, completed_at=time.time(),
        num_bars=len(bars), initial_capital=config.initial_capital,
        final_equity=equity_curve[-1], portfolio_metrics=portfolio_metrics,
        fusion_confusion=fusion_confusion, per_strategy_stats=per_strategy_stats,
        trades=closed_trades, equity_curve=equity_curve, decisions=decisions_log,
    )
    return report, time_in_regime_pct(regimes)


async def verify_regime_loop_matches_static_at_neutral_weights(
    bars: list[HistoricalBar], config: BacktestRunConfig,
) -> bool:
    """Sanity check: with every regime's weight vector set to neutral
    (1.0 for every strategy), this module's reimplemented loop must
    produce trade-for-trade identical results to the frozen, unmodified
    ``BacktestEngine().run()`` on the same bars — proving this is a
    faithful reimplementation of the same semantics, differing only in
    *which* weights get selected per bar, not in how trading works.
    """
    strategies = default_strategies()
    neutral_weights = {regime: {s.name: 1.0 for s in strategies} for regime in REGIMES}

    static_report = await BacktestEngine().run(bars, config)
    regime_report, _ = await run_regime_aware_backtest(bars, config, neutral_weights)

    sm, rm = static_report.portfolio_metrics, regime_report.portfolio_metrics
    return (
        sm.number_of_trades == rm.number_of_trades
        and abs(sm.total_return_pct - rm.total_return_pct) < 1e-6
        and abs(sm.sharpe_ratio - rm.sharpe_ratio) < 1e-6
        and abs(sm.max_drawdown_pct - rm.max_drawdown_pct) < 1e-6
    )
