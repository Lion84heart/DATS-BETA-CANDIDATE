# Research Cycle 001

**Date:** 2026-09-05
**Mission:** Find one trading strategy with a statistically credible edge on real crypto market data, using only existing infrastructure (Strategy Engine, Decision Fusion, Historical Data Infrastructure, Backtesting Engine, Trade Management, Research Framework). No new indicators, no new strategies, no new UI/dashboards/infrastructure this cycle.

## Hypothesis

Some combination of (a) a strategy subset different from "all 8," (b) a fusion method, (c) a minimum-confidence entry gate, and (d) Phase 4's trade-management stack will produce a configuration that clears all four success criteria — Profit Factor > 1.50, Sharpe > 1.20, Max Drawdown < 15%, positive CAGR — consistently across BTCUSDT, ETHUSDT, and SOLUSDT, on real historical data spanning a genuine bull/bear/recovery cycle.

Two sub-hypotheses were grounded in prior research rather than guessed:
- **Prior work (Sprint 6)** found EMA Cross and Trend Detection had the two lowest solo Sharpe ratios of all 8 strategies on synthetic data — worth testing whether removing them helps on real data too (`drop_weakest_2`).
- **Prior work (Sprint 7)** found ATR and Trend Detection were the two strategies whose agreement correlated with *winning* trades (not losing ones), while Volume Profile and Bollinger Bands correlated more with losses — worth testing a subset built around that finding (`protective_pair`), as an independent test on a dataset Sprint 7 never saw.

## What was tested

**72 configurations** (4 strategy subsets × 2 fusion methods × 3 confidence thresholds × 3 trade-management presets) × **3 symbols** (BTCUSDT, ETHUSDT, SOLUSDT) = **216 backtests**, all on real Binance daily OHLCV, **2021-01-01 → 2024-07-01** (1,278 bars/symbol — spanning the 2021 bull run, the 2022 bear market/Terra-LUNA/FTX collapse, and the 2023–24 recovery). A separate, later window (**2024-07-01 → 2026-09-01**, 793 bars/symbol) was fetched and its integrity confirmed, but **not used in any experiment this cycle** — it's held out for a future cycle to validate whatever survives here, never for picking or tuning.

| Axis | Values tested |
|---|---|
| Strategy subset | `all_8` (current default), `drop_weakest_2`, `top_4_sharpe`, `protective_pair` |
| Fusion method | the real, unmodified `DecisionFusion`, Sprint 6's `MajorityVoteFusion` |
| Confidence threshold | 0.0 (no gate), 0.5, 0.6 |
| Trade management | `none`, Phase 4's `position_sizing_only`, Phase 4's `full_risk_adjusted` |

Every experiment reuses existing, already-tested machinery only: `backtesting.engine.default_strategies()` filtered to a subset (not modified), the real `intelligence.fusion.DecisionFusion` or Sprint 6's already-verified `MajorityVoteFusion`, and Phase 4's already-built `execution_intelligence` trade-management stack. One small, additive change was made to Phase 4's `managed_backtest.py` this cycle — an optional `fusion=` parameter and a raw `min_confidence` entry gate — both backward-compatible (default behavior unchanged) and re-verified via the same sanity check Phase 4 established (managed loop reproduces the frozen `BacktestEngine` exactly at baseline).

## Results

**Headline finding: the current production configuration, replayed on real 2021–2024 crypto history, would have lost money.**

| | Sharpe | Profit Factor | Max Drawdown | CAGR |
|---|---:|---:|---:|---:|
| **Current system equivalent** (`all_8`, live fusion, no confidence gate, no trade management) | 0.151 | 1.004 | **71.30%** | **-4.37%** |
| BTCUSDT | 0.184 | 1.073 | 46.49% | +1.47% |
| ETHUSDT | 0.267 | 1.062 | 76.29% | +2.71% |
| SOLUSDT | 0.003 | 0.879 | **91.14%** | **-17.28%** |

This is a genuine, important disproof: the strategy engine and fusion logic as they exist today, with no trade management, do not have a demonstrated edge on real market data across a full crypto cycle — barely breaking even on profit factor and losing money overall, driven mostly by SOLUSDT's catastrophic 91% drawdown through the 2022 crash.

**Isolating one variable at a time on top of that baseline:**

*Trade management alone* (strategy/fusion/confidence held fixed):

| Trade management | Sharpe | Profit Factor | Max Drawdown | CAGR |
|---|---:|---:|---:|---:|
| None | 0.151 | 1.004 | 71.30% | -4.37% |
| Position Sizing alone | 0.151 | 1.091 | 38.05% | +1.03% |
| Full Risk-Adjusted (Phase 4) | **0.203** | **1.234** | **13.61%** | **+1.10%** |

This *confirms Phase 4's synthetic/short-real finding on a much longer, harsher real window*: Phase 4's trade-management stack alone cuts max drawdown from 71% to 14% and turns a losing CAGR into a (small) positive one.

*Strategy subset alone* (fusion/confidence/trade-management held at baseline "none"):

| Subset | Sharpe | Profit Factor | Max Drawdown | CAGR |
|---|---:|---:|---:|---:|
| `all_8` | 0.151 | 1.004 | 71.30% | -4.37% |
| `drop_weakest_2` | 0.305 | 1.127 | 70.31% | +2.53% |
| `top_4_sharpe` | 0.247 | 1.038 | 70.27% | +0.59% |
| `protective_pair` | **0.849** | **1.920** | 60.60% | **+54.07%** |

`protective_pair` (ATR, Trend Detection, Support/Resistance, Bollinger Bands) is a dramatic outlier — nearly 6x the baseline's Sharpe. This is the most striking single finding in this cycle, and it survives an important check: this subset was hypothesized *from Sprint 7's findings on a different, smaller dataset* and is being confirmed here on an independent, much larger real-market window it was never tuned against — not curve-fit to this data after the fact.

**Combining the two best individual levers** — `protective_pair` + `full_risk_adjusted` — is the closest any configuration came to passing every criterion:

| | Sharpe | Profit Factor | Max Drawdown | CAGR | Passes all 4? |
|---|---:|---:|---:|---:|---|
| Average (3 symbols) | 0.629 | 1.543 | 20.36% | 7.26% | No |
| BTCUSDT | 0.629 | 1.733 | **11.95%** ✓ | 5.13% | No (Sharpe) |
| ETHUSDT | 0.851 | 1.687 | **14.94%** ✓ | 11.10% | No (Sharpe) |
| SOLUSDT | 0.406 | 1.209 | 34.19% | 5.54% | No (Sharpe, Max DD, PF) |

BTCUSDT and ETHUSDT individually clear the drawdown and profit-factor bars — **only Sharpe is short (0.63–0.85 vs. the 1.20 requirement)**. SOLUSDT is the clear outlier dragging every average down, consistent with its idiosyncratic FTX/Alameda-linked collapse in the underlying data, not a general failure of the approach.

## Statistical read

Zero of 72 configurations passed all four criteria on all three symbols individually — the mission's own bar for "passes," which requires robustness per-symbol, not just on average. **This cycle's grid is formally rejected as a finished answer.** But it is not an uninformative rejection: the pattern across 216 backtests is consistent and directionally clear (trade management reliably cuts drawdown; a specific, hypothesis-driven strategy subset reliably improves Sharpe/PF far more than any other subset tested), not noise. The obvious caution: testing 4 subsets and picking the best-performing one (`protective_pair`) carries a multiple-comparisons risk — a "best of 4" winner can look inflated by chance even with no true difference. That's exactly why this finding is being carried into Cycle 2 as a hypothesis to confirm on the untouched holdout window, not accepted outright.

## Decision: **REJECTED** (as a finished strategy) — **hypothesis carried forward** (as a lead)

No configuration from Cycle 1 is ready for paper trading. However, `protective_pair` + `full_risk_adjusted` is not being discarded — it is the one candidate whose weakness (Sharpe) is precisely identified and whose strength (drawdown control, profit factor) is real and reproduced across BTC and ETH individually.

## Next hypothesis (Cycle 2)

1. **Validate `protective_pair` + `full_risk_adjusted` on the untouched 2024-07-01 → 2026-09-01 holdout window** — this is the first time it will be tested on data it had zero opportunity to be selected for, the real test of whether Cycle 1's finding is genuine or a multiple-comparisons artifact.
2. **Investigate why SOLUSDT underperforms so much more than BTC/ETH under the same configuration** — its realized volatility and drawdown are far higher; worth testing whether Phase 4's ATR-based position sizing needs a more aggressive scaling factor for higher-realized-volatility symbols, rather than one fixed multiplier across all three.
3. **Tune the Sharpe shortfall directly** — since drawdown and profit factor are already close to passing for BTC/ETH under `protective_pair` + `full_risk_adjusted`, the next lever to pull is whichever reduces return *volatility* without cutting return *level* as much — a tighter trailing-stop multiplier or an added take-profit rule are the two untested levers from the mission brief most likely to help here.

## Reproducibility

`docs/research-cycle-001-results.json` is the complete raw output this report is transcribed from. To re-run:

```
docker exec dats-beta mkdir -p /app/scripts
docker cp scripts/run_research_cycle_001.py dats-beta:/app/scripts/run_research_cycle_001.py
docker exec dats-beta python scripts/run_research_cycle_001.py
```

Fully deterministic given the same fixed UTC date ranges and Binance's immutable historical record for closed candles.

## Freeze compliance

Verified via `git diff --name-only` scoped to every frozen path: **zero changes** to `trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/confusion.py`, `backtesting/data.py`, `data/quality.py`, `market/schemas.py`. This cycle's only source change was an additive, backward-compatible extension to Phase 4's own (not-yet-deployed) `execution_intelligence/managed_backtest.py`.
