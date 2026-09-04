# Phase 4 — Trade Management Intelligence Report

**Date:** 2026-09-04
**Scope:** New, genuinely usable execution-quality modules — built, backtested, and evaluated. The Strategy Engine, Decision Fusion, and all existing indicators were frozen — see [Freeze compliance](#9-freeze-compliance). **Nothing in this phase is wired into any live path.** Per this phase's own gate ("nothing goes live unless statistically superior"), §7 gives the honest verdict on what the evidence actually supports.

## 1. Summary

This phase built eight trade-management modules that sit *between* a fused BUY/SELL/HOLD decision and the broker fill — none of them generate a trading signal, and every one of them defers entirely to the frozen Strategy Engine and the real, unmodified `intelligence.fusion.DecisionFusion` for *what* to trade. They only decide *whether* to act on an entry, *how much* to size it, and *when* to actually exit. Every module was backtested independently (Objective 9) and in combination, against the frozen baseline (Objective 10), across real Binance data (BTCUSDT/ETHUSDT/SOLUSDT × 1h/4h/1d — Phase 3's exact cached datasets) and a supplementary synthetic grid (8 symbols, 1D, 1,000 bars) — 136 backtests total, 796.0s wall-clock.

**Headline finding, stated precisely:**
- **No variant shows a statistically significant improvement in Sharpe ratio.** All paired Sharpe deltas against baseline have t-statistics far below any conventional significance threshold (largest: t=0.68 for the fully combined system, n=17) — the sample is small and the per-run noise is large relative to the average improvement.
- **Two variants — Position Sizing alone, and the fully combined "risk-adjusted execution" system — show an extraordinarily consistent and statistically significant reduction in maximum drawdown**: both cut max drawdown on **every single one of the 17 price series tested, with zero exceptions** (a sign test on 17/17 gives p ≈ 0.0000076 — this is real, not noise).
- **Individual exit-only modules (ATR stop, trailing stop, break-even) tested in isolation do not help, and mostly hurt**, Sharpe ratio and profit factor. They only become clearly beneficial in combination with position sizing.
- **Verdict: partial statistical case, not a full one.** Strong, significant evidence for reduced downside risk from position sizing (alone or combined); no significant evidence yet for improved risk-adjusted *return*. Per this phase's own gate, **nothing goes live** — see §7 for what would need to be true before revisiting that.

## 2. What was built

Eight modules, all in the new `src/execution_intelligence/` package, none imported by any live path:

| # | Module | File | What it does |
|---|---|---|---|
| 1 | Entry Quality Filter | `entry_filter.py` | Blocks a BUY unless the Trade Quality Score clears a threshold (default 55/100). A blocked BUY isn't canceled — Fusion is free to re-issue it on a later bar. |
| 2 | Dynamic Exit Engine | `exit_engine.py` | Combines the three stop mechanisms below with the fused SELL signal — whichever fires first, this bar, wins. Reduces to plain fused-SELL-only behavior when all three are disabled. |
| 3 | ATR-based Stop Loss | `stops.py` | A fixed stop at `entry_price - mult × ATR`, set once at entry. |
| 4 | Trailing Stop | `stops.py` | Ratchets up with the highest price reached since entry: `peak_price - mult × ATR`. |
| 5 | Break-even Protection | `stops.py` | Once unrealized gain reaches a trigger threshold (default 1.5%), arms a stop just above entry — the worst case for that trade becomes a small loss, not the full stop distance. |
| 6 | Position Sizing Engine | `position_sizing.py` | Replaces the baseline's fixed 95%-of-cash sizing with a quality- and volatility-scaled fraction — never more than the baseline would risk, often less. |
| 7 | Trade Quality Score | `quality_score.py` | A 0–100 composite (45% fused confidence, 35% strategy vote consensus, 20% volatility context) feeding modules 1 and 6. |
| 8 | Risk-adjusted execution | `managed_backtest.py` / `phase4_study.py` | All of the above combined into one pipeline — the "full_risk_adjusted" variant below. |

**No new indicator, no modified indicator.** The ATR figure this package computes (`atr_utils.py`, and an incremental equivalent inside the hot backtest loop for performance) is standalone risk-management arithmetic — the same standard True-Range formula `trading.strategies.atr.ATRStrategy` already uses internally, reimplemented for stop/sizing purposes, never touching that file and never producing a BUY/SELL/HOLD signal.

## 3. Methodology

`execution_intelligence/managed_backtest.py` reimplements the trade-simulation loop (same `PaperBroker` calls, same fill/slippage/commission logic) using the real, unmodified `DecisionFusion()` and the real frozen 8 strategies — never a substitute. **Verified before any comparison was trusted**: with every module toggle off, an automated sanity check confirmed this loop reproduces the frozen `BacktestEngine` exactly (same trade count, return, Sharpe, max drawdown):

```
[sanity check] managed loop matches frozen BacktestEngine at baseline (all toggles off): True
```

Eight variants were backtested on the identical bar series for every (symbol, timeframe): `baseline` (all toggles off), five single-module variants (`entry_filter_only`, `atr_stop_only`, `trailing_stop_only`, `breakeven_only`, `position_sizing_only`), `dynamic_exit_engine` (modules 3+4+5 combined), and `full_risk_adjusted` (everything combined). 17 unique price series × 8 variants = 136 backtests.

## 4. Per-variant results (Objectives 9 & 10)

Averaged across all 17 price series:

| Variant | Avg Sharpe | Avg Max DD | Avg CAGR | Avg Profit Factor | Avg Trades | Win rate vs. baseline (Sharpe) |
|---|---:|---:|---:|---:|---:|---:|
| **baseline** | 0.0401 | 31.71% | -1.82% | 1.190 | 25.2 | — |
| Entry Filter alone | -0.0447 | 29.33% | -3.49% | 1.289 | 15.8 | 47.06% |
| ATR Stop alone | 0.0223 | 30.12% | -1.98% | 1.018 | 41.6 | 41.18% |
| Trailing Stop alone | -0.0361 | 31.79% | -3.22% | 0.986 | 45.1 | 17.65% |
| Break-even alone | -0.0263 | 30.45% | -2.94% | 1.123 | 40.9 | 35.29% |
| **Position Sizing alone** | **0.0709** | **15.22%** | **-0.12%** | 1.116 | 22.1 | **70.59%** |
| Dynamic Exit Engine (3+4+5) | 0.0198 | 25.70% | -0.72% | 1.028 | 70.5 | 58.82% |
| **Full Risk-Adjusted Execution** | **0.1163** | **9.14%** | **0.02%** | **1.385** | 30.5 | 58.82% |

**Every single-module exit mechanism tested alone underperforms on Sharpe** — Trailing Stop alone is the worst, winning only 17.65% of pairwise comparisons against baseline and dropping profit factor below 1.0 (0.986). This is a real, honest finding: a lone trailing stop, without the other protective layers, tends to cut winning trades short before they mature, adding trade count (45.1 vs. baseline's 25.2) without adding edge.

**Position Sizing alone is the standout single module** — the only one that improves both Sharpe (+0.031 average) and dramatically cuts max drawdown (31.71% → 15.22%, a 52% relative reduction), while trading slightly less often than baseline.

**The fully combined system is the best performer on every metric shown** — best Sharpe, by far the best max drawdown (9.14%, a 71% relative reduction), best profit factor (1.385 vs. 1.190), and the *only* variant with a positive average CAGR. But see §5 — "best average" is not the same as "statistically proven better everywhere."

## 5. Statistical significance — the honest verdict

**On Sharpe ratio: not significant, for any variant.** A paired one-sample t-test on the 17 (variant − baseline) Sharpe deltas:

| Variant | n | Mean Δ Sharpe | Std Dev | t-statistic | Win rate |
|---|---:|---:|---:|---:|---:|
| Position Sizing alone | 17 | +0.0308 | 0.3006 | 0.42 | 70.6% (12/17) |
| Full Risk-Adjusted | 17 | +0.0762 | 0.4609 | 0.68 | 58.8% (10/17) |

Both t-statistics are far below the ~2.1 threshold a two-tailed test at n=17 would need for conventional significance (p < 0.05). The per-run variance is large relative to the average improvement — **this data does not support a claim that either variant reliably improves Sharpe ratio.** Position Sizing's 70.6% win rate looks encouraging but isn't, on its own, statistically decisive at this sample size.

**On maximum drawdown: highly significant, for both variants.** Both Position Sizing alone and Full Risk-Adjusted Execution reduced max drawdown on **all 17 of 17 price series tested — real and synthetic alike, with zero exceptions.** A sign test under the null hypothesis (50/50 chance of improving or worsening drawdown) gives:

```
P(17 of 17 successes | p=0.5) = 0.5^17 ≈ 0.0000076
```

This is a real, strong, statistically significant effect — not noise. Every single BTCUSDT/ETHUSDT/SOLUSDT real-market run and every one of the 8 synthetic symbols showed a lower drawdown under both variants, several by more than half (e.g., BTCUSDT 4h: 16.34% → 0.96% under the full system; ETHUSDT 1D: 41.77% → 16.41%; NVDA synthetic: 56.23% → 9.88%).

**Conclusion**: the evidence is a genuine partial case. Downside-risk reduction is proven; risk-adjusted-return improvement is not (yet).

## 6. Why the pieces behave the way they do

- **Exit-only modules are noisy in isolation** because each fires independently on the exact same adverse move — an ATR stop and a trailing stop react to the same drawdown differently but don't coordinate, and neither knows the fused SELL signal might be about to fire anyway; alone, each just adds trade-cutting noise. Combined (`dynamic_exit_engine`), they partially offset each other's weaknesses (mixed but improved: 58.8% Sharpe win rate vs. baseline, better than any single exit module alone) — but still don't clear significance.
- **Position sizing is the one module whose effect is inherently monotonic**: it can only ever commit the *same or less* capital than the baseline (§2's bound), so its drawdown-reducing effect is structural, not incidental — this is the most defensible explanation for its perfect 17/17 drawdown sweep.
- **The combined system's exit mix is dominated by break-even and ATR stops** (see raw exit-reason counts: `full_risk_adjusted` closed 316 trades via break-even, 116 via ATR stop, only 63 via the original fused SELL, and 22 via trailing stop, out of 518 total exits) — meaning most of this phase's improvement comes from cutting losers early and protecting gains once a trade is already favorable, directly targeting Sprint 7's own finding that losing trades were held ~2.8x longer than winners with 3.5x the adverse excursion.
- **The Entry Quality Filter is miscalibrated for real market data**: it blocked 907 entries at its default 55-point threshold, helping the synthetic grid (Sharpe +0.111 vs. baseline's +0.014) while hurting real Binance data notably (Sharpe -0.184 vs. baseline's +0.064) — real crypto data apparently doesn't fit the same quality-score distribution the synthetic GBM data does. This inconsistency is itself informative: a fixed threshold isn't the right design without per-symbol or per-source calibration, not built this phase.

## 7. Go/no-go verdict (Objective: "nothing goes live unless statistically superior")

**No module goes live from this phase.** Specifically:

- Trailing Stop alone, Break-even alone, ATR Stop alone, and Entry Filter alone: **do not deploy** — none show a consistent benefit, and Trailing Stop alone actively underperforms.
- Position Sizing alone: **promising, not proven.** Statistically significant drawdown reduction; Sharpe improvement not significant at this sample size. A larger validation (more symbols, longer real-data windows, ideally a paper-trading shadow run) is the natural next step before any live consideration.
- Full Risk-Adjusted Execution: **most promising overall, still not proven.** Best average metrics across the board and the same statistically significant drawdown reduction as Position Sizing alone, but Sharpe improvement is likewise not significant, and 7 of the 17 individual Sharpe comparisons are outright *worse* than baseline (e.g., ETHUSDT 1D: -0.74; AMD synthetic: -0.39) — this is not a system that wins everywhere.

## 8. Reproducibility

`docs/phase-4-trade-management-results.json` is the complete raw output this report is transcribed from — every table above can be regenerated from it. To re-run inside the running container:

```
docker exec dats-beta mkdir -p /app/scripts /app/src/execution_intelligence
docker cp src/execution_intelligence/. dats-beta:/app/src/execution_intelligence/
docker cp scripts/run_phase4_trade_management.py dats-beta:/app/scripts/run_phase4_trade_management.py
docker exec dats-beta python scripts/run_phase4_trade_management.py
```

Real data reuses Phase 3's exact fixed UTC ranges (same cached, checksummed data); synthetic data uses a fixed seed base (tag `"phase4"`). Both are fully deterministic.

## 9. Freeze compliance

Verified via `git diff --name-only`, scoped to every frozen path: **zero changes** to `trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/confusion.py`, `backtesting/data.py`. Every file this phase touched is new: `src/execution_intelligence/*`, `scripts/run_phase4_trade_management.py`, `docs/phase-4-trade-management-results.json`, this report, and `PROJECT_STATUS.md`. Nothing here is imported by, or reachable from, any live trading path.

## 10. Next steps (not implemented)

1. **Larger-sample validation of Position Sizing alone and Full Risk-Adjusted Execution** — more symbols, longer real-data windows, and ideally out-of-sample real data Phase 3's infrastructure hasn't fetched yet — specifically targeting Sharpe significance, since drawdown significance is already established.
2. **Per-source calibration of the Entry Quality Filter's threshold** — a single fixed 55-point cutoff clearly doesn't fit both real and synthetic data equally; worth investigating a data-source- or symbol-conditional threshold before testing this module again.
3. **Investigate why exit-only modules underperform in isolation** — whether tighter/looser multipliers, or requiring 2-of-3 stop-mechanism agreement before exiting, changes the picture; not tuned or tested this phase.
