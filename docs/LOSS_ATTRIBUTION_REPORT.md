# Sprint 7 — Loss Attribution & Edge Analysis Report

**Date:** 2026-09-04
**Scope:** Analysis only. The Trading Engine, Strategy Engine, and Decision Fusion were frozen for the entire sprint — see [Freeze compliance](#9-freeze-compliance). **No fixes are implemented in this sprint.** Every recommendation in §7 is a candidate for a future sprint to investigate, not a change made here.

## 1. Summary

This sprint analyzed **every losing trade** (314 of 927 total) produced by the frozen Strategy Engine and Decision Fusion, across a combined real + synthetic dataset: real Binance historical data (BTCUSDT/ETHUSDT/SOLUSDT × 1h/4h/1d — the exact fixed date ranges Phase 3 fetched and cached) plus a supplementary synthetic grid (Sprint 6/Phase 2's 8-symbol × 3-timeframe universe, 1,000 bars each). All numbers below are transcribed directly from `docs/sprint-7-loss-attribution-results.json`, the output of a single run of `scripts/run_loss_attribution.py` (129.8s wall-clock, 33 backtests, 927 trades analyzed).

**The headline finding is unambiguous and consistent across both real and synthetic data**: this strategy's losses are overwhelmingly a **timing problem**, not a directional-accuracy, overtrading, or trend-reversal problem.

- **80.57% of losing trades show a delayed entry** (bought measurably above the local price bottom) and **70.70% show a delayed exit** (sold measurably below the local price peak) — by a wide margin the two most common patterns.
- **Losing trades are held ~2.8x longer than winning trades** (28.08 bars vs. 10.14 bars, combined) — losses are not cut quickly.
- **Losing trades show 3.5x the adverse excursion of winning trades** (12.77% vs. 3.68% average MAE) but **lower favorable excursion** (3.80% vs. 6.64% average MFE) — losing trades mostly go wrong early and stay wrong, rather than being winners that reversed.
- Volatility spikes (40.13% of losers) and ranging markets (33.12% of losers) are real, secondary contributors. **Overtrading (5.10%) and trend reversal (4.78%) are minor factors** — this strategy is not losing money primarily because it trades too much or because trends flip against it.
- Decision Fusion's **entry** consensus is not meaningfully different between winners and losers, but its **exit** consensus is measurably lower on losing trades (0.311 vs. 0.339 combined; 0.315 vs. 0.386 on real data) — a coherent explanation for why exits are delayed: when a position is going badly, fewer of the 8 strategies flip to SELL, so the fused signal is slower to reach a majority.

## 2. Methodology

A new, research-only instrumented backtest loop (`research/trade_forensics.py`) reimplements `backtesting.engine.BacktestEngine.run()`'s exact trade-simulation logic — same `PaperBroker` calls, same position-sizing — using the **real, unmodified `intelligence.fusion.DecisionFusion`** (not a substitute, unlike Phase 2's research fusion variants) and the real, unmodified 8 strategies. It additionally records each strategy's raw per-bar signal, which the frozen engine discards after aggregating into its own summary stats. **Verified before the study ran**: an automated sanity check confirmed this loop produces trade-for-trade identical output (same trade count, same return, same Sharpe, same max drawdown) to the frozen `BacktestEngine` on the same bars:

```
[sanity check] forensic loop matches static BacktestEngine exactly: True
```

For every closed trade, `research/loss_classification.py` computes (pure post-hoc arithmetic over already-existing OHLCV bars — no new indicator, no new strategy):

- **MAE / MFE** (Maximum Adverse/Favorable Excursion): the worst/best price reached during the trade's life, as % of entry price.
- **Entry timing quality**: how far above the local low (a ±5-bar window around entry) the entry price was — 0% would mean buying at the exact local bottom.
- **Exit timing quality**: how far below the local high (a ±5-bar window around exit) the exit price was — 0% would mean selling at the exact local top.
- **Regime at entry and exit** (reusing Phase 2's causal, non-lookahead `research.regime.detect_regimes`, unmodified).
- **Vote agreement**: which of the 8 strategies voted the same direction as the fused decision at entry/exit.
- **Classification tags** (a losing trade can carry multiple): `trend_reversal`, `ranging_market`, `volatility_spike`, `delayed_entry`, `delayed_exit` (entry/exit timing worse than 1.0%), and a run-level `overtrading` flag (a run's trade frequency > 1.5× its own data-source's median, with below-median average holding time).

Every trade in this codebase is long-only (`PaperBroker` has no shorting), so every formula is long-only by construction.

## 3. Dataset

| | Trades | Losers | Winners | Loss rate |
|---|---:|---:|---:|---:|
| **Combined** | 927 | 314 | 613 | 33.87% |
| Real (Binance) only | 197 | 60 | 137 | 30.46% |
| Synthetic only | 730 | 254 | 476 | 34.79% |

A ~66% win rate is consistent with Decision Fusion's win rate in earlier sprints' research (Sprint 6: 71.89%; this sprint's slightly lower figure reflects a different, larger, and partly real-market sample). The loss rate is broadly similar between real and synthetic data (30–35%), which is itself a useful cross-check: the patterns below aren't an artifact of one data source.

## 4. Loss metrics (Objective 3)

| Metric | Losers (combined) | Winners (combined) | Losers (real) | Winners (real) |
|---|---:|---:|---:|---:|
| Avg. Adverse Excursion (MAE) | 12.77% | 3.68% | 8.28% | 1.93% |
| Avg. Favorable Excursion (MFE) | 3.80% | 6.64% | 2.11% | 3.44% |
| Avg. Holding Time (bars) | 28.08 | 10.14 | 26.27 | 14.53 |
| Entry timing quality (lower = better) | 5.78% | 4.03% | 2.90% | 2.28% |
| Exit timing quality (lower = better) | 5.28% | 4.86% | 2.61% | 2.36% |

The MAE/MFE asymmetry is the clearest single number in this report: losing trades have **more than 3x the downside excursion of winners, but less favorable excursion than winners**. A trade that goes on to lose money is, on average, a trade that went wrong quickly and never really worked — not a winning trade that gave back its gains.

### Largest losses (Objective 3)

Top 5 by absolute $ loss (of 15 captured in the raw JSON):

| Symbol | TF | Source | P&L | P&L % | MAE | MFE | Hold (bars) | Entry → Exit Regime | Tags |
|---|---|---|---:|---:|---:|---:|---:|---|---|
| AMD | 1W | synthetic | -$105,164 | -32.83% | 41.79% | 2.55% | 23 | High Vol → Trending Bear | volatility_spike, delayed_entry, delayed_exit, overtrading |
| MSFT | 1W | synthetic | -$94,701 | -45.34% | 49.01% | 17.73% | 20 | Trending Bear → Low Vol | delayed_entry, delayed_exit |
| AMZN | 1W | synthetic | -$74,677 | -17.60% | 25.27% | 8.63% | 16 | Trending Bear → Trending Bear | delayed_entry, delayed_exit |
| AMD | 1W | synthetic | -$74,601 | -26.12% | 39.35% | 12.15% | 21 | High Vol → High Vol | volatility_spike, delayed_entry, delayed_exit, overtrading |
| NVDA | 1W | synthetic | -$73,128 | -63.08% | 67.48% | 3.16% | 108 | Low Vol → Trending Bull | delayed_entry, delayed_exit |

Largest real-market loss: **ETHUSDT 1D, -$33,667 (-27.11%)**, entered during a Sideways regime, held 27 bars, MAE 38.08% — tagged `ranging_market`, `delayed_entry`, `delayed_exit`.

**Every one of the top 10 largest losses (both real and synthetic) carries both `delayed_entry` and `delayed_exit`** — the single most consistent thread across the worst individual outcomes in this study.

## 5. Repeated failure patterns (Objectives 3 & 6)

| Pattern | Combined (of 314 losers) | Real only (of 60) | Synthetic only (of 254) |
|---|---:|---:|---:|
| Delayed entry | 80.57% | 66.67% | 83.86% |
| Delayed exit | 70.70% | 61.67% | 72.83% |
| Volatility spike | 40.13% | 41.67% | 39.76% |
| Ranging market | 33.12% | 36.67% | 32.28% |
| Overtrading | 5.10% | 5.00% | 5.12% |
| Trend reversal | 4.78% | 3.33% | 5.12% |

The ranking is identical between real and synthetic data — delayed entry/exit dominate, volatility and ranging conditions are meaningful secondary factors, and overtrading/trend-reversal are marginal. This consistency across two very different data sources (real crypto, synthetic GBM) is evidence the pattern is structural to how the Strategy Engine and Decision Fusion currently react to price action, not an artifact of one dataset.

**Two runs were flagged for overtrading** (trade frequency > 1.5× their data-source's own median, with below-median holding time): SOLUSDT 1D (real, 4.79 trades/100 bars, avg hold 9.74 bars) and AMD 1W (synthetic, 4.60 trades/100 bars, avg hold 10.72 bars). Two runs out of 33 is a small, specific finding — overtrading is not a general problem in this dataset.

## 6. Strategy contribution (Objective 4)

For every trade, "agreement" means a strategy voted the same direction as the fused entry (BUY) or exit (SELL) decision. The **delta** (agree-rate on losers minus agree-rate on winners) is the signal: a strategy whose votes track losing trades more than winning trades is more implicated in losses; a negative delta means the opposite — that strategy's agreement is associated with *better* outcomes.

| Strategy | Delta (combined) | Delta (real only) | Read |
|---|---:|---:|---|
| Volume Profile | +0.0636 | +0.1691 | Most associated with losing entries, especially on real data |
| Bollinger Bands | +0.0549 | +0.1237 | Second most associated with losing entries |
| VWAP | +0.0262 | +0.0534 | Mildly associated with losing entries |
| Support/Resistance | +0.0260 | +0.0372 | Mildly associated with losing entries |
| RSI | +0.0093 | -0.0158 | Roughly neutral |
| EMA Cross | +0.0012 | +0.0187 | Roughly neutral |
| Trend Detection | -0.0407 | -0.0951 | Associated with *better* outcomes when it agrees |
| ATR | -0.0631 | -0.0794 | Most associated with *better* outcomes when it agrees |

Volume Profile and VWAP have very high raw agreement rates with both winners and losers (0.83–0.88) simply because they trade most often (consistent with Sprint 6's finding that they average 11+ trades per run, far more than the other six strategies) — their *delta* is what isolates a real effect, not their raw agreement rate. **Volume Profile and Bollinger Bands are the two strategies whose agreement most consistently coincides with losing trades, especially on real market data. ATR and Trend Detection show the opposite pattern — their agreement coincides with winning trades more than losing ones.** This is directionally consistent with Phase 2's independently-derived regime-routing research, which up-weighted ATR specifically in both volatility regimes and down-weighted Volume Profile/Bollinger Bands' relative influence in several regimes — two separate analyses arriving at compatible conclusions from different methods.

## 7. Decision Fusion contribution (Objective 5)

| | Losers | Winners | Difference |
|---|---:|---:|---:|
| Entry consensus (combined) | 0.3296 | 0.3199 | +0.0097 (losers slightly *higher*) |
| Exit consensus (combined) | 0.3109 | 0.3395 | -0.0286 (losers lower) |
| Entry consensus (real only) | 0.3604 | 0.3339 | +0.0265 (losers slightly *higher*) |
| Exit consensus (real only) | 0.3146 | 0.3859 | -0.0713 (losers notably lower) |

**Fusion's entry decisions are not meaningfully weaker-consensus on trades that go on to lose** — if anything, losing trades entered with marginally *higher* agreement among the 8 strategies, the opposite of what "Fusion enters on shaky signals" would predict. The real signal is on the **exit** side: losing trades exit with measurably lower SELL-vote consensus than winning trades (a 0.071 gap on real data — the largest single gap in this table). Combined with §4's holding-time finding, this paints a coherent picture: **it is not that Decision Fusion's blending logic makes bad entries — it's that when a position is already going wrong, fewer of the 8 strategies flip to SELL, so the fused signal is slow to reach a majority and the loss is held longer than a winning trade would have been.** This implicates the *exit-side behavior of the underlying strategies* more than Decision Fusion's combination rule itself, which is doing the same confidence-weighted vote either way.

## 8. Cause detection summary (Objective 6)

| Cause | Evidence found? | Magnitude |
|---|---|---|
| Delayed entries | **Yes — dominant** | 80.57% of losers (66.67% real, 83.86% synthetic) |
| Delayed exits | **Yes — dominant** | 70.70% of losers (61.67% real, 72.83% synthetic) |
| Volatility spikes | **Yes — secondary** | 40.13% of losers |
| Ranging markets | **Yes — secondary** | 33.12% of losers |
| Overtrading | Marginal — 2 runs only | 5.10% of losers |
| Trend reversals | Marginal | 4.78% of losers |

## 9. Freeze compliance

Verified via `git diff --name-only`, scoped to every previously-frozen path: **zero changes** to `trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/confusion.py`, `backtesting/data.py`, `data/quality.py`, `market/schemas.py`. Every file this sprint touched is new: `src/research/trade_forensics.py`, `src/research/loss_classification.py`, `src/research/loss_attribution_study.py`, `scripts/run_loss_attribution.py`, `docs/sprint-7-loss-attribution-results.json`, this report, and `PROJECT_STATUS.md`. **No fix, parameter change, or behavioral change was made anywhere in the trading path this sprint.**

## 10. Actionable recommendations (Objective 7 — analysis only, nothing implemented)

These are candidates for a **future** sprint to investigate and decide on — not changes made here:

1. **Investigate exit-signal responsiveness.** §7's finding — exit consensus is measurably lower on losing trades, and §4/§5 show losers are held ~2.8x longer with 3.5x the adverse excursion of winners — points at the exit side, not the entry side, as the highest-leverage place to look. Worth researching whether the fused SELL threshold could react faster once a position is already showing significant adverse excursion, without touching entry logic.
2. **Investigate entry-timing sensitivity.** 80.57% of losers show a delayed entry. Worth researching whether the strategies that fire earliest into a losing entry (Volume Profile, VWAP — §6) are reacting to noise rather than a durable move, versus the strategies that showed a *protective* pattern (ATR, Trend Detection).
3. **Cross-reference with Phase 2's regime-routing research.** This sprint independently found Volume Profile/Bollinger Bands more associated with losses and ATR/Trend Detection more associated with wins — directionally consistent with Phase 2's regime-conditional weight recommendations (never deployed, per that phase's own near-tie finding). A future sprint could re-run Phase 2's regime-aware comparison using *this* sprint's loss-attribution evidence as an additional signal, rather than Phase 2's edge scores alone.
4. **Research a maximum-adverse-excursion-based stop.** There is currently no risk-based exit anywhere in the trading path — a position only closes on a fused SELL signal. Losers' 12.77% average MAE (vs. winners' 3.68%) suggests a cap on adverse excursion could meaningfully change the loss profile — worth a dedicated research sprint (with real backtested evidence, not assumption) before ever being implemented.
5. **Deprioritize overtrading and trend-reversal fixes.** Both are minor factors here (5.10% and 4.78% of losers respectively) — any future sprint's limited effort is better spent on §1–§3 above.

## 11. Reproducibility

`docs/sprint-7-loss-attribution-results.json` is the complete raw output this report is transcribed from — every table above can be regenerated from it. To re-run the study inside the running container:

```
docker exec dats-beta mkdir -p /app/scripts
docker cp scripts/run_loss_attribution.py dats-beta:/app/scripts/run_loss_attribution.py
docker exec dats-beta python scripts/run_loss_attribution.py
```

The real-data portion reuses Phase 3's exact fixed UTC date ranges (same cached, checksummed data); the synthetic portion uses a fixed seed base (via `research.study`, tag `"loss-attribution"`). Both are fully deterministic — re-running reproduces this report's numbers exactly.
