# Phase 3 — Historical Data Infrastructure Report

**Date:** 2026-09-04
**Scope:** New infrastructure only. The Trading Engine, Strategy Engine, and Decision Fusion were frozen for the entire phase — see [Freeze compliance](#7-freeze-compliance). This phase introduces real market data; it does not change how any signal, fusion decision, or trade is generated.

## 1. Summary

This phase built a Historical Data Service that fetches **real** historical OHLCV from Binance's public API, validates it, caches it to disk, and converts it into the exact `HistoricalBar` shape the existing (frozen) `BacktestEngine` already consumes from its synthetic and CSV-import sources. Every number in this report is transcribed from `docs/phase-3-data-infrastructure-results.json`, the output of a live run of `scripts/run_historical_data_infra.py` against Binance's real API (14.9s wall-clock, 9 real network fetches, 1 cache-hit re-fetch, 1 real backtest).

**What was actually proven, live, not just built and asserted:**
- **9 real datasets fetched** — 3 symbols (BTCUSDT, ETHUSDT, SOLUSDT) × 3 timeframes (1h, 4h, 1d) — all integrity-clean (zero rejected rows, zero duplicate timestamps, zero timeline gaps).
- **Pagination proven, not just coded**: the 1h fetches (60-day range) returned 1,441 bars each, which is more than Binance's 1,000-bar-per-request cap — meaning the client's pagination logic genuinely executed a second page on every 1h fetch, not just a single-request path.
- **Caching proven**: a second fetch of the same (symbol, interval, range) returned in 0.018s vs. the first fetch's 0.953s (a ~53x speedup) with `cache_hit=True`.
- **Reproducibility proven, not asserted**: the two independent fetches' SHA-256 checksums matched exactly — `49a5c8484e346d0580d31421a631bb7b2d31a5a7704e225ee724f058bcdea8c8` both times.
- **The frozen `BacktestEngine` ran on real market data for the first time in this project's history** — real BTCUSDT daily bars (2025-08-01 → 2026-09-01), through the unmodified engine, unmodified 8-strategy Decision Fusion: 397 bars, 7 trades, **-16.45% total return, Sharpe -0.376, max drawdown 29.31%**. This is a losing result, reported exactly as computed — real market data doesn't guarantee a flattering backtest, and this report doesn't pretend otherwise.

## 2. Architecture

New package `src/historical_data/`, four modules, each with one job:

| Module | Responsibility |
|---|---|
| `binance_client.py` | Real async REST client for Binance's public `/api/v3/klines` endpoint (no API key required). Mirrors the existing `market.coingecko_connector.CoinGeckoConnector`'s retry/backoff/pacing pattern. Paginates automatically past Binance's 1,000-klines-per-request cap. |
| `integrity.py` | Validates raw klines. Reuses two **existing, unmodified** pieces of infrastructure instead of reimplementing validation: `market.schemas.OHLCVBar`'s own Pydantic validators (rejects bad high/low relationships, non-positive prices, negative volume at construction time) and `data.quality.DataQualityEngine` (gap detection via `check_completeness`, price-outlier flagging via `detect_outliers`). |
| `cache.py` | On-disk, checksummed cache under `data/historical_cache/` (inside the same mounted `./data` volume every other durable piece of this app's state already lives in) — one JSON file + one manifest per (source, symbol, interval, start, end) key. |
| `service.py` | `HistoricalDataService.get_ohlcv(...)` — the single entry point: check cache → fetch if missing → validate → convert to `backtesting.data.HistoricalBar` (the frozen dataclass, reused unmodified) → return, ready for `BacktestEngine.run()`. |

**Why disk, not the app's existing Redis cache:** `infra.redis_client.RedisManager` is already used elsewhere in this codebase and would have been a reasonable choice for "cache datasets." It was deliberately not used here: Objective 9 ("produce reproducible research datasets") needs the exact same bytes to still exist whenever someone re-reads a report citing them, not just for as long as a TTL keeps them warm. A historical dataset that a research report cites is a durable artifact, so it gets the same kind of durable, checksummed store the rest of this app's persisted state (`data/decisions.db`) already uses — Redis remains the right tool for hot, short-lived state, just not this one.

**Why no changes to `backtesting/data.py`:** it already defines `HistoricalBar` and already supports two data sources (synthetic, CSV import) alongside whatever `BacktestEngine.run()` is handed — this phase adds a third source *outside* that file, producing the identical `HistoricalBar` type, so `backtesting/data.py` needed zero changes and stays exactly as Sprint 5 left it.

## 3. Real historical OHLCV import (Objectives 2–5)

Live fetch results (fixed, past UTC date ranges — never "now minus N days" — so the exact same dataset is reproducible at any future re-run date):

| Symbol | Interval | Range (UTC) | Bars | Fetch time | Integrity |
|---|---|---|---:|---:|---|
| BTCUSDT | 1h | 2026-07-01 → 2026-08-30 | 1,441 | 2.61s | Clean |
| BTCUSDT | 4h | 2026-05-01 → 2026-08-30 | 727 | 1.13s | Clean |
| BTCUSDT | 1d | 2025-08-01 → 2026-09-01 | 397 | 0.95s | Clean |
| ETHUSDT | 1h | 2026-07-01 → 2026-08-30 | 1,441 | 2.07s | Clean |
| ETHUSDT | 4h | 2026-05-01 → 2026-08-30 | 727 | 1.44s | Clean |
| ETHUSDT | 1d | 2025-08-01 → 2026-09-01 | 397 | 0.92s | Clean |
| SOLUSDT | 1h | 2026-07-01 → 2026-08-30 | 1,441 | 1.85s | Clean |
| SOLUSDT | 4h | 2026-05-01 → 2026-08-30 | 727 | 0.96s | Clean |
| SOLUSDT | 1d | 2025-08-01 → 2026-09-01 | 397 | 1.38s | Clean |

**Multiple symbols (Objective 4):** 3 distinct symbols (BTCUSDT, ETHUSDT, SOLUSDT) — Binance's own trading pairs, no synthetic seed-price mapping involved. **Multiple timeframes (Objective 5):** 3 distinct intervals (1h, 4h, 1d), exercising both the pagination path (1h, 2 pages) and the single-request path (4h, 1d).

## 4. Data integrity validation (Objective 8)

Across all 9 datasets: **zero rejected rows, zero duplicate timestamps, zero timeline gaps** (no candle wider than 1.5× the expected interval anywhere in any series). Every row survived construction as a `market.schemas.OHLCVBar`, meaning every row's high/low/open/close/volume relationship was independently validated by that model's own Pydantic validators, not just trusted from the API response.

**One honest caveat on the outlier counts** (BTCUSDT 1h: 280 flagged, ETHUSDT 1h: 311, SOLUSDT 1h: 213, SOLUSDT 4h: 21): these are **not** data-quality defects. `DataQualityEngine.detect_outliers` (reused unmodified) applies a single IQR bound across the *entire* series' close prices. Over a 60-day 1h window where price trended meaningfully, a large fraction of later bars legitimately fall outside the *early-window* IQR band — this is a known characteristic of applying a static-window outlier test to raw price *levels* on a trending series, not evidence of bad rows. Every one of those "outlier" bars still passed the strict `OHLCVBar` construction validation (real, internally-consistent OHLC relationships) — they were flagged and reported, not silently dropped, exactly as the code's own docstring says: "informational only, not rejected." A more precise trend-aware outlier check (e.g. on returns rather than levels) is flagged as a possible future improvement, not built here — this phase reused the existing `DataQualityEngine` exactly as it already works, rather than extending it.

## 5. Caching and reproducibility (Objectives 6 & 9)

Directly measured, not asserted:

| | First fetch (live) | Second fetch (same key) |
|---|---:|---:|
| Source | Binance API | Disk cache |
| Time | 0.953s | 0.018s (~53x faster) |
| `cache_hit` | `False` | `True` |
| SHA-256 | `49a5c848...dea8c8` | `49a5c848...dea8c8` (identical) |

The cache stores both the raw kline rows and a manifest (`source`, `symbol`, `interval`, time range, row count, SHA-256 checksum, fetch timestamp) under `data/historical_cache/` — inside the same persistent volume `data/decisions.db` already survives container restarts in. A checksum mismatch on read is treated as a cache miss (triggers a fresh fetch), so a corrupted or hand-edited cache file can never silently masquerade as the original dataset — reproducibility is verified on every read, not just at write time.

## 6. Feeding the existing Backtest Engine (Objective 7)

Real BTCUSDT daily data (2025-08-01 → 2026-09-01, 397 bars) was passed to `backtesting.engine.BacktestEngine().run(bars, config)` — **the exact same unmodified class Sprint 5 built and Sprint 6/Phase 2 already reused**, with its default 8 strategies and live `DecisionFusion`, zero changes:

| Metric | Value |
|---|---:|
| Bars | 397 |
| Trades | 7 |
| Total Return | -16.45% |
| CAGR | -10.78% |
| Sharpe Ratio | -0.376 |
| Max Drawdown | 29.31% |
| Profit Factor | 0.498 |
| Win Rate | 57.14% |

This is the first time any backtest in this project has run on real market data instead of synthetic GBM. **The result is a loss, reported exactly as computed.** This isn't a claim the Strategy Engine or Decision Fusion "don't work" — one 13-month window on one symbol is not a strategy evaluation (that's what Sprint 5/6's much larger synthetic studies were for) — it's evidence the new data pipeline hands the frozen engine real, unmanipulated data and lets it do whatever it does with it, good or bad, exactly like every synthetic run before it.

## 7. Freeze compliance

Verified via `git diff --name-only`, scoped to every previously-frozen path plus the two existing modules this phase *reused* (`data/quality.py`, `market/schemas.py`): **zero changes** to `trading/strategies/`, `trading/execution/`, `intelligence/fusion.py`, `intelligence/engine.py`, `api/routers/execution.py`, `api/routers/orders.py`, `backtesting/engine.py`, `backtesting/metrics.py`, `backtesting/confusion.py`, `backtesting/data.py`, `data/quality.py`, `market/schemas.py`. Every file this phase touched is new: `src/historical_data/*`, `scripts/run_historical_data_infra.py`, `docs/phase-3-data-infrastructure-results.json`, this report, and `PROJECT_STATUS.md`.

## 8. Reproducibility

`docs/phase-3-data-infrastructure-results.json` is the complete raw output this report is transcribed from. To re-run against live Binance data inside the running container:

```
docker exec dats-beta mkdir -p /app/scripts /app/src/historical_data
docker cp src/historical_data/. dats-beta:/app/src/historical_data/
docker cp scripts/run_historical_data_infra.py dats-beta:/app/scripts/run_historical_data_infra.py
docker exec dats-beta python scripts/run_historical_data_infra.py
```

Every date range is a fixed past UTC window, so re-running this at any later date fetches the identical closed candles — Binance's historical record for a closed candle doesn't change — and should reproduce this report's bar counts, integrity results, and checksums exactly (the backtest result will also reproduce exactly, since `BacktestEngine` and `PaperBroker` fills are deterministic given identical input bars).

## 9. Known limitations / next steps

- Only Binance is supported as a live source (Objective 3). CSV import for non-Binance historical data already exists (`backtesting.data.parse_csv_ohlcv`, Sprint 5, untouched) as a separate, pre-existing path — this phase didn't need to add anything there.
- The outlier check (§4) is a static-window IQR test on price levels, inherited as-is from the existing `DataQualityEngine` — a return-based or rolling-window version would be more precise on trending series, not built this phase.
- `HistoricalDataService` has no symbol/interval *discovery* endpoint (e.g. "list what's tradeable on Binance") — callers must already know the Binance symbol string (e.g. `BTCUSDT`) and a valid interval code.
- No API route was added to trigger a fetch from the UI — this phase is a backend/research-facing service, consistent with "Do not change trading logic" and with the fact that nothing here was asked to be user-facing.
