# Phase 2 — Market Regime Engine Research Report

**Date:** 2026-09-04
**Scope:** Research only. The trading engine, all eight existing strategies, and Decision Fusion were frozen for the entire phase — see [Freeze compliance](#8-freeze-compliance). No routing change is deployed to live trading.

## 1. Summary

This phase built a Market Regime Engine — causal, bar-by-bar detection of five market regimes from OHLCV data, plus a regime-conditional strategy-weighting scheme derived from real backtested evidence — and backtested it head-to-head against the existing static system (all 8 strategies fused by the unmodified, live `DecisionFusion`) on out-of-sample synthetic data. All numbers below are transcribed directly from `docs/phase-2-regime-results.json`, the raw output of `scripts/run_regime_research.py` (48 backtests: 24 static + 24 regime-aware, 394.9s wall-clock).

**Headline finding — reported honestly, not spun:** regime-aware routing does **not** show a clear, decisive improvement over the static system. Averaged across all 24 (symbol, timeframe) pairs, Sharpe is essentially tied (0.1723 regime-aware vs. 0.1715 static), while regime-aware trades ~30% more often (37.6 vs. 29.0 avg trades), has a slightly *worse* max drawdown (38.34% vs. 37.72%), a *lower* profit factor (1.144 vs. 1.228), and a *lower* win rate (59.07% vs. 65.33%). It does win more head-to-head matchups by Sharpe (13 of 24 vs. 11 of 24) and shows a higher average CAGR/total return — but that's consistent with trading more often on a mildly-drifting synthetic series, not necessarily better risk-adjusted skill. **This phase's own evidence does not support deploying regime-aware routing over the current static system**, and the report says so directly rather than framing a near-tie as a win.

A likely explanation, visible in the data itself: the regime-conditional "edge" scores the routing weights are built from cluster tightly around 44%–55% (barely above the 50% coin-flip baseline) for every strategy in every regime — see [§6](#6-regime-conditional-edge-scores). The underlying data is synthetic GBM with a small constant drift; a geometric random walk has no genuine autocorrelation structure for a technical strategy to exploit differently by "regime" beyond what regime detection already captures indirectly through volatility. The routing weights are real, data-derived, and directionally sensible (see §7), but they're built on a thin statistical edge, which is the most likely reason the final backtest comparison is a near-tie rather than a clear win.

## 2. Methodology

### 2.1 Regime detection (`src/research/regime.py`)

Five regimes — Trending Bull, Trending Bear, Sideways, High Volatility, Low Volatility — detected per bar using only close prices already in the (frozen) `HistoricalBar` series. No new indicator or strategy is introduced; this is market classification, not a trading signal:

1. **Trend** — trailing 20-bar return.
2. **Realized volatility** — stdev of 1-bar returns over the trailing 20 bars.
3. Both are **z-scored against their own trailing 100-bar history** (computed strictly before the current bar), so thresholds adapt per-symbol rather than using one hardcoded number across differently-scaled price series.
4. **Volatility takes precedence over trend**: |z| > 1.0 on volatility labels High/Low Volatility regardless of trend direction (a volatility extreme makes a "trend" reading unreliable); only bars with unremarkable volatility are then classified by trend (|z| > 0.5 → Bull/Bear, else Sideways).
5. Bars without enough trailing history (first ~120 bars of a run) default to Sideways.

This is **fully causal** — label[i] depends only on bars[0..i] — so replaying it bar-by-bar in a backtest never sees the future.

### 2.2 Regime-conditional routing weights (`src/research/regime_router.py`)

For each (strategy, regime) pair, an **edge score** — the support-weighted average of BUY-signal precision and SELL-signal precision *specifically on bars of that regime* — is computed by reusing the frozen `backtesting.confusion.compute_confusion_matrix` unmodified: bars outside the target regime are masked to a sentinel value excluded from that regime's tabulation, while the close-price series stays fully intact so forward-horizon lookups remain valid. Edge scores are averaged across all 8 symbols, then converted to a weight vector per regime via the same normalize → rescale-to-mean-1 → clip[0.3, 2.0] → re-center method Sprint 6 used for its overall recommended weights (with an added final clamp — see the code comment in `_weights_from_edge` — since per-regime samples are noisier than Sprint 6's single overall average and could otherwise push a weight slightly past 2.0 after re-centering).

**Out-of-sample discipline:** weights were fit on one seed series (tag `regime-fit`, 2,000 bars/symbol, 1D) and evaluated on a *different* seed series (tag `regime-eval`, 1,000 bars/(symbol, timeframe)) — the comparison in §3–5 is not graded on the same data the weights were derived from.

### 2.3 Regime-aware backtest loop (`src/research/regime_backtest.py`)

`backtesting.engine.BacktestEngine.run()` calls one fixed `DecisionFusion.combine()` for an entire run — it has no per-bar hook to vary fusion weights by regime, and it is frozen this phase. `run_regime_aware_backtest()` is a new, research-only function that reimplements the identical trade-simulation loop (same `PaperBroker` calls, same position-sizing, same trade bookkeeping, same frozen `compute_portfolio_metrics`/`compute_confusion_matrix`), differing only in one place: each bar's fusion call uses `WeightedFusion(weights_by_regime[detected_regime])` (Sprint 6's already-verified `DecisionFusion` generalization) instead of one fixed weighting for the whole run.

**This reimplementation is directly verified, not just asserted equivalent.** Before the study ran, an automated sanity check (`verify_regime_loop_matches_static_at_neutral_weights`) set every regime's weights to neutral (1.0 for all 8 strategies) and confirmed the regime-aware loop produces **trade-for-trade identical** output (same trade count, same total return, same Sharpe, same max drawdown) to the frozen, unmodified `BacktestEngine().run()` on the same bars:

```
[sanity check] regime-aware loop matches static BacktestEngine at neutral (1.0) weights: True
```

This confirms the only behavioral difference from the static system in every result below is *which weights get selected per bar*, not a divergent reimplementation of trading logic.

### 2.4 Comparison grid

8 symbols × 3 timeframes (1H/1D/1W) × 1,000 bars, evaluated twice per (symbol, timeframe): once with the frozen `BacktestEngine()` (static, live `DecisionFusion`), once with the regime-aware router — both on the identical bar series, so the only difference is the fusion/weighting mechanism.

## 3. Overall comparison (Objective 4)

Averaged across all 24 (symbol, timeframe) pairs:

| Metric | Static (`DecisionFusion`) | Regime-Aware Routing | Delta |
|---|---:|---:|---:|
| **Sharpe Ratio** | 0.1715 | 0.1723 | +0.0008 (essentially tied) |
| **Max Drawdown** | 37.72% | 38.34% | +0.62pp (worse) |
| **CAGR** | 0.76% | 1.18% | +0.42pp (better) |
| **Profit Factor** | 1.228 | 1.144 | -0.084 (worse) |
| Total Return | 10.80% | 14.28% | +3.48pp |
| Win Rate | 65.33% | 59.07% | -6.26pp (worse) |
| Avg. Trades/run | 29.0 | 37.6 | +30% more trades |

**Read honestly:** of the four requested comparison metrics, regime-aware routing is essentially tied on Sharpe, worse on max drawdown, better on CAGR, and worse on profit factor. It is not a clean win on any reasonable combined read — the higher CAGR/total return comes with more trades, a lower win rate, and a lower profit factor, consistent with routing simply trading more often rather than trading more *skillfully*.

## 4. Symbol-specific and timeframe-specific performance (Objectives 3 & 6-ish)

**By symbol** (avg Sharpe across 3 timeframes) — a 4-4 tie:

| Symbol | Static Sharpe | Regime-Aware Sharpe | Winner |
|---|---:|---:|---|
| AAPL | 0.318 | 0.189 | Static |
| MSFT | 0.376 | 0.229 | Static |
| GOOGL | 0.308 | 0.364 | Regime-Aware |
| TSLA | 0.402 | 0.544 | Regime-Aware |
| NVDA | 0.186 | 0.118 | Static |
| AMZN | -0.035 | -0.087 | Static |
| META | -0.228 | -0.143 | Regime-Aware |
| AMD | 0.044 | 0.163 | Regime-Aware |

**By timeframe** (avg across 8 symbols):

| Timeframe | Static Sharpe | Regime Sharpe | Static MaxDD | Regime MaxDD | Static PF | Regime PF |
|---|---:|---:|---:|---:|---:|---:|
| 1H | 0.249 | 0.236 | 8.59% | 8.36% | 1.560 | 1.361 |
| 1D | -0.077 | -0.098 | 42.17% | 38.87% | 0.906 | 0.880 |
| 1W | 0.343 | 0.379 | 62.41% | 67.78% | 1.219 | 1.193 |

Regime-aware routing is slightly worse at 1H and 1D, and slightly better at 1W — no consistent pattern across timeframes. (Note the 1D row shows both variants with Sharpe below zero and profit factor below 1.0 — this specific out-of-sample seed series was a losing environment for both systems, which is itself useful evidence this study isn't cherry-picking a favorable dataset.)

## 5. Head-to-head win count

Comparing all 24 individual (symbol, timeframe) pairs directly by Sharpe: **regime-aware wins 13, static wins 11.** A slim, not-statistically-decisive edge in win *count* that doesn't show up as a decisive edge in the *averaged* metrics in §3 — small individual wins and losses roughly offset.

## 6. Regime-conditional edge scores

The edge scores (support-weighted BUY/SELL precision, on a 0–100 scale where 50 = coin flip) that the routing weights in §7 are built from, averaged across all 8 symbols on the fit series:

| Regime | Highest-edge strategy | Score | Lowest-edge strategy | Score |
|---|---|---:|---|---:|
| Trending Bull | Support/Resistance | 54.95 | ATR | 46.98 |
| Trending Bear | Bollinger Bands | 53.84 | ATR | 46.69 |
| Sideways | Bollinger Bands | 54.06 | EMA Cross | 47.54 |
| High Volatility | EMA Cross | 55.32 | Support/Resistance | 44.25 |
| Low Volatility | EMA Cross | 52.22 | Support/Resistance | 45.66 |

Every score in every regime falls in a narrow 44%–55% band. That's a real but thin statistical edge — nowhere near strong enough to expect a routing scheme built on it to produce a dramatic overall performance change, which is consistent with §3's near-tie result. This is a property of the underlying synthetic GBM price data (a random walk with small constant drift has limited genuine regime-conditional structure for a rule-based strategy to exploit), not evidence the regime *detector* itself is broken — time-in-regime is well-balanced across all 5 regimes for every symbol (18%–24% each, see raw JSON `fit_metadata.time_in_regime_by_symbol_pct`), confirming the detector is actually discriminating between regimes rather than defaulting to one label.

## 7. Recommended regime routing weights (Objective 2)

Data-derived, out-of-sample-evaluated, clipped to [0.3, 2.0]:

| Strategy | Trending Bull | Trending Bear | Sideways | High Vol | Low Vol |
|---|---:|---:|---:|---:|---:|
| RSI | 1.454 | 1.614 | 0.322 | 0.537 | 0.488 |
| EMA Cross | 1.695 | 1.302 | 0.322 | 2.000 | 1.803 |
| VWAP | 0.569 | 0.597 | 0.754 | 0.594 | 0.989 |
| ATR | 0.300 | 0.300 | 0.531 | 1.544 | 1.471 |
| Bollinger Bands | 0.898 | 1.946 | 2.000 | 0.976 | 0.921 |
| Support/Resistance | 1.794 | 1.061 | 2.000 | 0.301 | 0.300 |
| Volume Profile | 0.841 | 0.756 | 0.574 | 0.457 | 1.146 |
| Trend Detection | 0.459 | 0.432 | 1.204 | 1.587 | 0.893 |

Several of these are directionally consistent with textbook trading intuition even though the method is purely empirical, not theory-asserted: **ATR (a volatility-breakout strategy) is down-weighted to the floor (0.3) in both trend regimes and up-weighted in both volatility regimes** (1.544 High Vol, 1.471 Low Vol); **Bollinger Bands and Support/Resistance (both range/mean-reversion-oriented) are up-weighted to the ceiling (2.0) in Sideways** and down-weighted in High Volatility. Not every entry matches textbook expectation (e.g. Support/Resistance also scores highly in Trending Bull) — this is presented as real, computed output, not smoothed to match theory.

## 8. Freeze compliance

Verified via `git diff --name-only`, scoped to every frozen path (`trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/confusion.py`, `backtesting/data.py`): **zero changes**, confirmed both before this report was written and again immediately before commit. Every file this phase touched is new: `src/research/regime.py`, `src/research/regime_router.py`, `src/research/regime_backtest.py`, `src/research/regime_study.py`, `scripts/run_regime_research.py`, `docs/phase-2-regime-results.json`, this report, and `PROJECT_STATUS.md`.

## 9. Reproducibility

`docs/phase-2-regime-results.json` is the complete raw output this report is transcribed from. To re-run the study from scratch inside the running container:

```
docker exec dats-beta mkdir -p /app/scripts
docker cp scripts/run_regime_research.py dats-beta:/app/scripts/run_regime_research.py
docker exec dats-beta python scripts/run_regime_research.py
```

The run is fully deterministic (fixed seed bases inherited from `research.study`), so re-running it reproduces this report's numbers exactly.

## 10. Conclusion and recommendation

**Do not deploy regime-aware routing to live trading based on this phase's evidence.** The Market Regime Engine works as built — detection is causal and well-balanced across regimes, the routing weights are real and largely intuitive, and the regime-aware backtest loop is verified to be a faithful reimplementation of the frozen engine's semantics — but the resulting head-to-head comparison against the current static system is a near-tie at best, and a regression on max drawdown and profit factor at worst. Two directions could be worth a future phase's investigation rather than this one:

1. **Stronger regime-conditional edges are needed before routing can help.** §6 shows every strategy's per-regime edge is close to a coin flip on this synthetic GBM data. A study on real historical OHLCV (via the existing `parse_csv_ohlcv` CSV-import path, already supported by the frozen `backtesting.data` module) might reveal more exploitable regime-conditional structure than a random-walk simulator can.
2. **A larger fit/eval sample** — this phase used 2,000 fit bars and 1,000 eval bars per series; both are modest relative to the noise visible in the per-(symbol, timeframe) results in §4.

Neither of the above is implemented in this phase — both are flagged here as open questions for whoever picks this up next, consistent with reporting only what was actually run and found.
