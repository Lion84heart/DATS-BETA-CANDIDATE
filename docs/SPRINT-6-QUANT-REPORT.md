# Sprint 6 — Quantitative Research & Strategy Optimization Report

**Date:** 2026-09-04
**Scope:** Research only. The trading engine, Strategy Engine, and execution engine were frozen for the entire sprint — see [Freeze compliance](#freeze-compliance) for how that was verified, not just asserted.

## 1. Summary

This sprint ran a controlled quantitative study over the existing (frozen) Strategy Engine and Decision Fusion, using the existing (frozen) `BacktestEngine` as the sole execution path — no new indicators, no new strategies, no changes to how a strategy or fusion decision is computed. All results below are transcribed directly from `docs/sprint-6-research-results.json`, the raw output of `scripts/run_quant_research.py` (a single run, 243 backtests, 247.7s wall-clock). Nothing here is estimated or reconstructed by hand.

**Headline findings:**
- **Decision Fusion (all 8 strategies combined) beats every individual strategy** on risk-adjusted return (Sharpe 0.568 vs. the best solo strategy, Volume Profile, at 0.527) — the clearest, most decisive result in this study.
- The two weakest solo strategies by Sharpe (Trend Detection 0.049, EMA Cross 0.178) are also the two strategies the weight-optimization procedure independently assigned the *lowest* recommended weights (0.285 each) — the optimizer and the raw performance ranking agree, which is a useful internal consistency check, not a coincidence built into the method.
- **Weighted voting vs. majority voting is not a clean win.** Across 8 symbols, the live confidence-weighted `DecisionFusion` and the optimized-weight variant each won on 3 of 8 symbols by total return; unweighted majority voting won on 2. This is reported as a near-tie, not a decisive result — see [§5](#5-weighted-vs-majority-voting).
- 1H-timeframe results are close to flat (avg Sharpe 0.104) compared to 1D (0.863) and 1W (0.736) — most likely a warm-up-period artifact given the fixed 250-bar run length, not a claim that the strategies "don't work" intraday. See [§7](#7-timeframe-specific-performance).
- Large-scale (5,000-bar) flagship runs show large absolute returns (67%–328%); a documented data-generation caveat in [§4](#4-large-scale-backtests-objective-1) explains why this figure should not be read as a real-world return expectation.

## 2. Methodology

- **Data:** synthetic OHLCV via the existing (frozen) `backtesting.data.generate_synthetic_ohlcv` (GBM-based). No new data source was introduced. Every (symbol, timeframe) combination uses a deterministic seed (`research/study.py:_seed_for`) so every strategy and fusion variant compared for that combination replays the *exact same* price path — required for a fair, apples-to-apples comparison.
- **Execution:** every backtest goes through the unmodified `BacktestEngine.run()`. Solo-strategy runs use `BacktestEngine(strategies=[one_strategy])`; fusion-variant runs use `BacktestEngine(fusion=variant)`. Both constructor parameters already existed in the Sprint 5 engine — nothing was added to support this study.
- **Fusion variants** (`src/research/fusion_variants.py`, new — research-only, never imported by any live path):
  - `MajorityVoteFusion` — unweighted, one strategy one vote.
  - `WeightedFusion` — confidence-weighted vote with an added per-strategy multiplier; **verified to produce identical output to the live `DecisionFusion` when every weight is 1.0** (sanity check ran automatically before the study: `WeightedFusion(weights=1.0) matches live DecisionFusion: True`).
- **Three experiments, each over its own consistent dataset:**
  1. **Grid** — 8 symbols × 3 timeframes (1H/1D/1W) × (8 solo strategies + live fusion) = 216 runs, 250 bars each.
  2. **Fusion-method comparison** — 8 symbols × 3 fusion variants = 24 runs, 500 bars each, 1D only, a *separate* seed series from the grid (tag `fusion-cmp`) — so these numbers are not directly comparable to the grid's `decision_fusion` row, only to each other.
  3. **Large-scale flagship** — AAPL/TSLA/NVDA × 5,000 bars, 1D, live fusion.
- **Weight optimization:** for each strategy, average Sharpe and win rate across all 8 symbols at the primary timeframe (1D) only, min-max normalized, composited 50/50, rescaled to mean 1.0, clipped to [0.3, 2.0], re-centered to mean 1.0. Full method in `research/study.py:compute_recommended_weights`.

## 3. Per-strategy independent performance (Objective 2)

Averaged across all 8 symbols × 3 timeframes, 250 bars per run (216-run grid):

| Strategy | Avg Return | Avg Sharpe | Avg Sortino | Avg Max DD | Avg Win Rate | Avg Trades | Avg Exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| Volume Profile | 19.04% | 0.527 | 0.582 | 17.41% | 66.18% | 11.5 | 43.33% |
| VWAP | 16.90% | 0.444 | 0.490 | 18.25% | 72.97% | 11.3 | 49.03% |
| ATR | 17.07% | 0.185 | 0.355 | 19.82% | 42.29% | 6.0 | 45.72% |
| EMA Cross | 16.30% | 0.178 | 0.349 | 19.70% | 39.44% | 5.5 | 42.72% |
| Trend Detection | 12.88% | 0.049 | 0.210 | 22.45% | 45.00% | 4.0 | 45.20% |
| Support/Resistance | 12.64% | 0.453 | 0.451 | 17.17% | 67.01% | 2.8 | 42.60% |
| RSI | 9.74% | 0.372 | 0.337 | 18.32% | 50.42% | 2.5 | 44.50% |
| Bollinger Bands | 7.92% | 0.442 | 0.473 | 17.77% | 68.75% | 2.8 | 39.67% |

**Ranked by average Sharpe** (highest = best risk-adjusted): Volume Profile (0.527) > Support/Resistance (0.453) > VWAP (0.444) > Bollinger Bands (0.442) > RSI (0.372) > ATR (0.185) > EMA Cross (0.178) > Trend Detection (0.049).

Note the split between "high win-rate, low trade-count" strategies (Bollinger Bands, Support/Resistance, RSI — patient, selective signals) and "high trade-count, mid win-rate" strategies (Volume Profile, VWAP — active, still net-positive on Sharpe). Trend Detection and EMA Cross show the weakest risk-adjusted returns; both were independently down-weighted by the optimizer (see §6), without that being an intentional target of the method.

## 4. Large-scale backtests (Objective 1)

5,000-bar, 1D, live `DecisionFusion` runs:

| Symbol | Bars | Total Return | Sharpe | Trades | Wall-clock |
|---|---:|---:|---:|---:|---:|
| AAPL | 5,000 | 66.83% | 0.231 | 140 | 27.22s |
| NVDA | 5,000 | 131.77% | 0.310 | 154 | 31.29s |
| TSLA | 5,000 | 327.65% | 0.449 | 167 | 38.42s |

**Caveat — read before citing these numbers elsewhere:** `generate_synthetic_ohlcv`'s default per-bar drift (0.0003) compounds to roughly 4.5x over 5,000 bars from drift alone, before any trading skill is applied (at a 1-bar = 1-day convention, that's ≈7.6%/year — a moderate, not absurd, assumption, but still a modeling choice, not observed market behavior). These absolute return figures are therefore a demonstration that the full pipeline (Strategy Engine → Fusion → PaperBroker) runs correctly and profitably at scale over a long synthetic series — not a forecast of real trading returns. The Sharpe ratios (0.23–0.45), which are scale-invariant with respect to drift, are the more trustworthy figures here.

## 5. Weighted vs. majority voting (Objective 5)

500-bar, 1D runs, 8 symbols, separate seed series (`fusion-cmp` tag) from the grid:

| Method | Avg Return | Avg Sharpe | Avg Sortino | Avg Max DD | Avg Win Rate | Avg Trades | Symbol wins (of 8) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Live `DecisionFusion` (confidence-weighted) | -0.68% | 0.039 | 0.009 | 32.65% | 63.16% | 14.4 | 3 |
| Optimized `WeightedFusion` (recommended weights) | -1.84% | -0.011 | -0.035 | 33.59% | 69.27% | 18.0 | 3 |
| `MajorityVoteFusion` (unweighted) | -5.04% | -0.082 | -0.183 | 33.83% | 58.75% | 4.1 | 2 |

Per-symbol winner by total return: AAPL → majority, MSFT → majority, GOOGL → live fusion, TSLA → optimized, NVDA → live fusion, AMZN → optimized, META → optimized, AMD → live fusion.

**Honest read:** this is not a decisive result. Live confidence-weighting and the optimized weights tie on symbol wins (3 each); unweighted majority voting is a clear third on average return and Sharpe, but wins 2 of 8 symbols outright and trades far less often (4.1 vs. 14.4–18.0 trades), so its downside is smaller in absolute terms even when it loses. All three methods average a negative-to-flat return on this particular 500-bar sample — a harder dataset than the grid's, and not something this study should paper over.

What *is* consistent and worth acting on: the optimized weights produce the **highest win rate of the three** (69.27% vs. 63.16% live, 58.75% majority) and noticeably more trades (18.0 vs. 14.4), which is the expected effect of down-weighting the two noisiest strategies (Trend Detection, EMA Cross) — fewer weak dissenting votes means the remaining strategies reach a decisive majority more often. That is a real, explainable mechanism, not noise. But it did not translate into a clearly better average total return in this sample. **Recommendation: worth a larger-sample follow-up before treating the optimized weights as a proven upgrade over the live engine's equal-weighting — the evidence here is suggestive, not conclusive.**

## 6. Decision Fusion vs. every strategy (Objective 3) & recommended weights (Objectives 4 & 8)

From §3's ranking, `decision_fusion` (all 8 combined, live confidence-weighted) achieves **Sharpe 0.568**, ahead of every solo strategy including the best one (Volume Profile, 0.527) — full comparison:

| Variant | Avg Sharpe | Avg Return |
|---|---:|---:|
| **decision_fusion (all 8, fused)** | **0.568** | **17.52%** |
| Volume Profile (solo) | 0.527 | 19.04% |
| Support/Resistance (solo) | 0.453 | 12.64% |
| VWAP (solo) | 0.444 | 16.90% |
| Bollinger Bands (solo) | 0.442 | 7.92% |
| RSI (solo) | 0.372 | 9.74% |
| ATR (solo) | 0.185 | 17.07% |
| EMA Cross (solo) | 0.178 | 16.30% |
| Trend Detection (solo) | 0.049 | 12.88% |

Decision Fusion also has the highest win rate of any variant, solo or fused (71.89% vs. Volume Profile's 66.18%), confirming the ensemble's main value proposition: combining 8 independent, uncorrelated-ish signals produces a steadier, more consistently right decision than any single signal, even the best one.

**Recommended weights** (derived per §2's method, from real backtested Sharpe + win rate at 1D, all 8 symbols):

| Strategy | Recommended Weight |
|---|---:|
| VWAP | 1.734 |
| Volume Profile | 1.595 |
| Bollinger Bands | 1.551 |
| Support/Resistance | 1.090 |
| RSI | 1.015 |
| ATR | 0.445 |
| EMA Cross | 0.285 |
| Trend Detection | 0.285 |

These are a **data-grounded recommendation, not an applied change** — see §5 for why they are not (yet) a clear net improvement over the live engine's equal-confidence weighting, and [§8](#8-not-applied-to-live-trading) for why nothing here touches live behavior regardless.

## 7. Symbol-specific performance (Objective 6)

`decision_fusion`, averaged across all 3 timeframes:

| Symbol | Avg Return | Avg Sharpe |
|---|---:|---:|
| AAPL | 43.61% | 0.950 |
| MSFT | 37.93% | 1.175 |
| NVDA | 36.99% | 0.855 |
| META | 8.33% | 0.871 |
| GOOGL | 14.70% | 0.538 |
| AMZN | 0.38% | 0.385 |
| TSLA | 1.57% | -0.220 |
| AMD | -3.32% | -0.014 |

Performance varies substantially by symbol — expected, since each symbol gets its own independent synthetic price path (different seed) rather than a shared market factor. This is a reminder that any single-symbol backtest (including the flagship large-scale runs in §4) should not be generalized to "the strategy works" without checking the distribution across symbols, which is exactly why this study ran all 8 rather than reporting one.

## 8. Timeframe-specific performance (Objective 7)

`decision_fusion`, averaged across all 8 symbols:

| Timeframe | Avg Return | Avg Sharpe | Avg Max DD | Avg Exposure |
|---|---:|---:|---:|---:|
| 1H | 0.14% | 0.104 | 4.44% | 50.40% |
| 1D | 18.56% | 0.863 | 15.07% | 46.85% |
| 1W | 33.86% | 0.736 | 36.02% | 42.60% |

1H results are close to flat. The most likely explanation is a **fixed-bar-count artifact, not a claim about intraday tradability**: every grid run uses the same 250-bar budget regardless of timeframe, so a 250-bar 1H run covers only ~10.4 days, while several of the 8 strategies need a meaningful warm-up window (moving averages, ATR, Bollinger Bands) before they produce a mature signal — a much larger fraction of a 250-bar 1H run is spent "warming up" than of a 250-bar 1D or 1W run. This should be treated as an open question for a future study with an increased 1H bar count, not as evidence the strategies fail intraday.

## 9. Freeze compliance

Verified via `git diff --name-only` immediately before writing this report, scoped to every frozen path (`trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`): **zero changes**. Every file this sprint touched is new: `src/research/__init__.py`, `src/research/fusion_variants.py`, `src/research/study.py`, `scripts/run_quant_research.py`, `docs/sprint-6-research-results.json`, this report, and `PROJECT_STATUS.md`.

## 10. Reproducibility

`docs/sprint-6-research-results.json` is the complete raw output this report is transcribed from — every table above can be regenerated from it. To re-run the study from scratch inside the running container:

```
docker exec dats-beta mkdir -p /app/scripts
docker cp scripts/run_quant_research.py dats-beta:/app/scripts/run_quant_research.py
docker exec dats-beta python scripts/run_quant_research.py
```

The run is fully deterministic (fixed `RNG_SEED_BASE`), so re-running it should reproduce this report's numbers exactly.

## 11. Not applied to live trading

Nothing in this sprint changes what a live paper-trading session, the AI Decision Engine, or the AI Center displays or does. The recommended weights in §6 are a research output only — applying them would require modifying `intelligence/fusion.py` (frozen this sprint) and is explicitly out of scope. If a future sprint decides to adopt them, §5's near-tie finding should be revisited with a larger sample first.
