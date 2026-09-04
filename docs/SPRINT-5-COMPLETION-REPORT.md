# Sprint 5 Completion Report — Backtesting & Evaluation Framework

**Date:** 2026-09-04
**Scope:** A professional backtesting framework that replays historical OHLCV data through the *exact* live Strategy Engine and Decision Fusion, simulates trades via the *exact* live `PaperBroker`, and produces the full required set of performance/evaluation statistics with CSV/JSON export and a new UI page.
**Constraints honored:** no new trading strategies, no new indicators — the new `backtesting/` package contains zero signal-generation logic of its own; it only replays data through the eight strategies and fusion module Sprint 4 already built, unmodified.

## Design decision: reuse, not reimplement

The single most important engineering decision this sprint: **the backtest doesn't approximate live trading — it runs the live trading code.**

- **Signal generation**: the same 8 `BaseStrategy` instances from `trading/strategies/` (`RSIStrategy`, `EMACrossStrategy`, `VWAPStrategy`, `ATRStrategy`, `BollingerBandsStrategy`, `SupportResistanceStrategy`, `VolumeProfileStrategy`, `TrendDetectionStrategy`), called via the exact same `generate_signal(df, features={})` interface the live `AIDecisionEngine` uses.
- **Fusion**: the exact same `DecisionFusion.combine()` from `intelligence/fusion.py` — objective 3 ("execute the existing Decision Fusion exactly as in live mode") is satisfied by literal code reuse, not a re-implementation that could drift from live behavior.
- **Trade simulation**: the exact same `PaperBroker` class from `trading/execution/paper_broker.py` that live Paper Trading uses — same fill logic, same slippage/commission model, same no-shorting guard — via a **fresh, isolated instance per backtest run**. This instance is never registered anywhere and is discarded when the run completes, so it structurally cannot affect the live registry's shared broker (verified below).

This means a backtest result reflects precisely what the live system would have done over the replayed period — the strongest possible guarantee that backtest and live behavior stay consistent, and it's why "no new strategies/indicators" was easy to honor: there was no reason to write any.

One existing file, `trading/backtest.py`, already implements a *different* single-strategy long/short backtesting engine (used by `trading/ab_testing.py` and `trading/optimization.py`). It was left completely untouched — this sprint's `backtesting/` package is a new, separate, complementary tool for the specific "replay through live Fusion + PaperBroker" requirement, not a replacement.

## What was built

**`src/backtesting/data.py`** — Two historical data sources: `parse_csv_ohlcv()` for real historical data supplied as CSV (`timestamp/date/time,open,high,low,close,volume`), and `generate_synthetic_ohlcv()` for when no file is available, using the existing `MarketSimulator` (the same GBM engine already driving live paper trading's simulated feed) — sampling several intrabar sub-steps per bar to produce genuine open/high/low/close, unlike live's single-tick bars which collapse to high=low=close. Both paths are clearly labeled for what they are; synthetic data is never presented as real market history.

**`src/backtesting/metrics.py`** — `compute_portfolio_metrics()` produces all eleven required metrics (Total Return, CAGR, Win Rate, Profit Factor, Sharpe Ratio, Sortino Ratio, Max Drawdown, Average Trade, Average Hold Time, Exposure, Number of Trades) from the equity curve and closed-trade list, using standard formulas with each bar treated as one trading day (252 bars/year) for annualization — a documented convention, not a hidden assumption.

**`src/backtesting/confusion.py`** — `compute_confusion_matrix()` builds a real 3×3 confusion matrix (predicted BUY/SELL/HOLD vs. actual subsequent price move, classified UP/DOWN/FLAT over a configurable forward-looking horizon and threshold) from data already present in the backtest — there's no external "ground truth" for a trading signal, so "actual" is defined the standard backtesting way: what the price genuinely did next.

**`src/backtesting/engine.py`** — `BacktestEngine.run()` replays bars one at a time: feeds each into the broker's `on_price_tick` (so it can fill orders), runs all 8 strategies, fuses them, and — on a fused BUY with no existing position — buys with a configurable fraction of available cash; on a fused SELL while holding — sells the full position. Every strategy call is individually wrapped in try/except (one broken strategy can't crash a run or silently vanish from the vote), and the loop yields to the event loop every 50 bars so a long run can't starve other requests.

**`src/backtesting/report.py`** — `report_to_dict()`/`report_to_json()`/`dict_to_csv()`. The CSV is a single file with clearly labeled sections (portfolio metrics, fusion confusion matrix, per-strategy statistics, trades) since a backtest report has several distinct tabular shapes that don't fit one flat table.

**`src/intelligence/decisions.py`** — `DecisionStore` gained a `backtest_runs` table (`save_backtest_run`/`get_backtest_run`/`list_backtest_runs`) in the same `decisions.db` established in Sprint 3 — every run is persisted with its full report as a JSON blob plus indexed summary columns for listing.

**`src/api/routers/backtest.py`** (new) — `POST /backtest/run` (Operator+, runs and persists a backtest; caps at 5,000 bars), `GET /backtest/runs` (list, Viewer+), `GET /backtest/runs/{id}` (full report), `GET /backtest/runs/{id}/export.json`, `GET /backtest/runs/{id}/export.csv`.

**Frontend — new Backtesting page**: symbol/data-source/bar-count/capital config form, a Run button, an 11-stat-card metrics grid, a Fused Signal Confusion Matrix table, a Per-Strategy Statistics table, a Trades table with client-side JSON/CSV download, and a Past Runs history table (click "View" to reload any prior run). Built with the exact same `.card`/`.data-table`/`.stat-card`/badge components used everywhere else in the app.

## Verification

All verification was against the real running Docker stack, rebuilt after the change and loaded from a fresh never-before-cached loopback address. Clean boot, no import/syntax errors.

| Check | Result |
|---|---|
| Full run performance | 500 bars × 8 strategies + fusion + broker fills completed in ~2 seconds via the real API. |
| Genuine, non-cherry-picked output | One run showed a realistic **loss** (Total Return −19.83%, Sharpe −0.38, 16 trades, 50% win rate) — not a suspiciously clean success, exactly what an honestly-computed backtest against random synthetic data should sometimes show. |
| Confusion matrix math (hand-verified) | BUY precision 40.34% = 71 correct / 176 support, computed independently and matched the API's output exactly; support totals (176+135+184=495) matched 500 bars − 5-bar horizon exactly. |
| Trade record correctness | A sample trade's `exit_time − entry_time` (777,600 seconds) matched `(exit_bar − entry_bar) × 86,400s` (9 bars × 1 day) exactly. |
| Per-strategy independence | All 8 strategies' BUY+SELL+HOLD counts summed to exactly the bar count (500) in every case, and showed genuinely different distributions (e.g. `vwap`: 263/205/32 vs. `ema_cross`: 13/14/473) — confirming independent, non-duplicated computation. |
| CSV import (real historical data path) | Parsed and replayed an 80-row hand-built CSV successfully — confirms objective 1's literal "replay historical data" path, not just the synthetic generator. |
| CSV/JSON export | `GET .../export.csv` returned a well-formed multi-section CSV (verified content directly); `GET .../export.json` (and the UI's JSON download) returns the full report. |
| Persistence | 3 backtest runs (2 synthetic, 1 CSV-imported) were all still listed via `GET /backtest/runs` after a full `docker restart` of the app container. |
| **Live Trading unchanged — verified, not assumed** | After running multiple backtests generating 24+ simulated trades total, `GET /portfolio/` (the live registry broker) still showed exactly $100,000.00 cash, 0 positions, 0 commission — confirming the backtest's broker instance is fully isolated. No file under `api/routers/execution.py`, `api/routers/orders.py`, or the live broker/feed code paths was modified this sprint. |
| UI end-to-end | Ran a backtest via the actual Run button (not just the API); all 11 metric cards, the confusion matrix table, per-strategy table, and trades table rendered correctly, confirmed via screenshot. Past Runs list correctly showed prior runs with a working "View" reload. |
| Regression sweep | Clicked through all seven pages (six existing + new Backtesting) in both Live and Demo Mode after the rebuild — zero console errors. |
| Health check | `GET /health/` → `decisions_available: healthy` after the schema change (new `backtest_runs` table alongside `decisions`/`strategy_results`). |

## What was deliberately left alone

- **`trading/backtest.py`** (the pre-existing single-strategy long/short engine used by `ab_testing.py`/`optimization.py`) — untouched; a different tool for a different purpose.
- **No new strategies or indicators** — confirmed by construction: `backtesting/` imports the 8 existing strategy classes and `DecisionFusion` without modification; it contains no `generate_signal`-shaped logic of its own.
- **No multi-symbol/portfolio backtesting** — one symbol per run, matching the single-position model the live Paper Trading page and `PaperBroker` already use.
- **No walk-forward/out-of-sample UI** — `trading/backtest.py` already has `run_walk_forward()` for that (different engine); not duplicated here.
- **Live execution code untouched** — `api/routers/execution.py`, `api/routers/orders.py`, `trading/execution/paper_broker.py` (used, not modified), and the live feed/broker registry components were not changed.
