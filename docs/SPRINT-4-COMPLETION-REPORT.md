# Sprint 4 Completion Report — Strategy Engine

**Date:** 2026-09-04
**Scope:** A modular Strategy Engine of eight independent technical-analysis strategies (RSI, EMA Cross, VWAP, ATR, Bollinger Bands, Support/Resistance, Volume Profile, Trend Detection), each producing its own BUY/SELL/HOLD with confidence and reasoning, combined by a new Decision Fusion module into one final recommendation. Every individual strategy result and the final fused decision are stored and displayed in AI Center.
**Constraint honored:** no LLM, no OpenAI, no Claude, no external AI API anywhere in this codebase — verified by construction (every strategy is a closed-form technical-analysis formula over local price/volume data) and by inspection (no HTTP calls, no API keys, no new dependencies of any kind added this sprint).

## What was built

### The Strategy Engine — `src/trading/strategies/`

Eight new strategy classes, each implementing the existing `BaseStrategy` interface (`trading/base_strategy.py`) already used by the codebase's pre-existing strategies. Unlike those (which return `None` when they have nothing to say), every strategy here **always returns a signal** — BUY, SELL, or HOLD — because the sprint's objective is explicit that each strategy must independently produce all three. When a strategy doesn't have enough history yet, it returns an honest low-confidence HOLD explaining exactly why (e.g. *"RSI: only 9/15 bars available — insufficient history"*) rather than staying silent or guessing.

| # | Strategy | File | Signal logic |
|---|---|---|---|
| 1 | RSI | `rsi.py` | 14-period RSI; BUY < 30 (oversold), SELL > 70 (overbought), confidence scales with distance past the threshold. |
| 2 | EMA Cross | `ema_cross.py` | EMA(9)/EMA(21); BUY/SELL on an actual crossover *event* this bar (not just current relative position), HOLD otherwise. |
| 3 | VWAP | `vwap.py` | Volume-weighted average price over a rolling window; BUY when price is meaningfully below VWAP, SELL when above. |
| 4 | ATR | `atr.py` | Average True Range as a volatility breakout filter — BUY/SELL when price has moved more than 1.5x ATR over a lookback window. |
| 5 | Bollinger Bands | `bollinger.py` | SMA(20) ± 2σ; BUY at/below the lower band, SELL at/above the upper band, confidence from %B. |
| 6 | Support/Resistance | `support_resistance.py` | Rolling min/max over a window; BUY near support, SELL near resistance. |
| 7 | Volume Profile | `volume_profile.py` | Bins recent closes by traded volume to find the Point of Control (POC); BUY below POC, SELL above. |
| 8 | Trend Detection | `trend_detection.py` | Least-squares linear regression over the window; BUY/SELL on a strong, consistent slope (R² gate), distinct from EMA Cross's event-based approach. |

**A documented, honest data limitation:** the AI Decision Engine's tick-derived bars carry `high = low = close` (a single price tick has no intrabar range). ATR and Support/Resistance are written against the full OHLC contract (`ohlcv_df["high"]`/`["low"]`), so the math is standard and correct — it just currently operates on a degenerate range, a known and common simplification when only close-level data is available (not a fabricated result). This is called out in both files' docstrings.

### Decision Fusion — `src/intelligence/fusion.py`

`DecisionFusion.combine()` takes the eight independent `StrategySignal`s and produces one `FusedDecision` via **confidence-weighted majority voting**: each strategy's vote counts in proportion to its own confidence (with a small floor so unanimous-but-low-confidence fields still resolve decisively), the direction with the highest total weight wins, and the fused confidence is that direction's share of the total vote weight. The reasoning string is fully auditable — it lists exactly which strategies voted which way and their average confidence, e.g.:

> *"Fused decision: SELL (77% weighted agreement). SELL 2/8 (avg 100%): vwap, support_resistance; HOLD 6/8 (avg 10%): rsi, ema_cross, atr, bollinger_bands, volume_profile, trend_detection"*

This is deterministic arithmetic, not a model — the same eight inputs always produce the same fused output.

### Storage — `src/intelligence/decisions.py`

Added a `strategy_results` table to the existing `decisions.db` SQLite database (built in Sprint 3), with `save_strategy_results()` / `get_strategy_results()` on `DecisionStore`. One row per (fused decision, strategy) — eight rows per analysis pass, linked by `decision_id` — so every individual strategy's signal/confidence/reasoning is queryable independently of the fused outcome it fed into, satisfying "store every individual strategy result" as its own, separate requirement from "store the final fused decision" (which reuses Sprint 3's existing `decisions` table/DecisionRecord unchanged).

### Engine rewrite — `src/intelligence/engine.py`

`AIDecisionEngine._analyze()` now: runs all eight strategies against the buffered OHLCV window (each wrapped in its own try/except so one broken strategy can't crash the pass or silently vanish from the vote), fuses their outputs, records the fused decision through the existing `DecisionPipeline` (unchanged — still `REVIEW_REQUIRED`, still advisory-only, still never touches `/orders/`), and persists all eight individual results via the new `save_strategy_results()`. `MomentumStrategy` (Sprint 3's original solo strategy) is untouched in the codebase but is no longer part of the live analysis loop — the Strategy Engine's fused decision is now "the" AI recommendation.

### API — `src/api/routers/decisions.py`

New `GET /decisions/{decision_id}/strategies` returns the full per-strategy breakdown behind one fused decision. `GET /decisions/{decision_id}` and `GET /decisions/` also now surface `signal`/`risk_level` consistently (a couple of fields the Sprint 3 router had missed adding to the single-decision endpoint).

### Frontend — AI Center

New **Strategy Engine Breakdown** card (`index.html`, `app.js`) between the recommendation cards and Decision History — a table of all 8 strategies' Signal/Confidence/Reasoning for the currently displayed fused decision, fetched via the new endpoint. Uses the same `data-table`/badge components already used everywhere else in the app — no new visual language. Demo Mode extended with an illustrative 8-row breakdown (`DEMO.strategyBreakdown`) — still never touches the real backend.

## Verification

All verification was against the real running Docker stack, rebuilt after the change and loaded from a fresh never-before-cached loopback address to guarantee real network fetches. Clean boot with no import/syntax errors across all 8 new strategy modules plus the fusion module.

| Check | Result |
|---|---|
| Every strategy always returns BUY/SELL/HOLD | Confirmed via `GET /decisions/{id}/strategies`: with limited history, all 8 strategies returned explicit low-confidence HOLDs stating exactly how many bars were available vs. required (e.g. "13/15", "13/23", "13/25") — never null, never silently skipped. |
| Independent, differentiated signals | As history accumulated, strategies diverged exactly as expected for real, distinct formulas: in one snapshot VWAP and Support/Resistance both independently reached SELL (100% confidence each, different reasoning: "10.98% above VWAP" vs. "within 0.50% of resistance") while the other six were still warming up; in a later snapshot RSI independently flagged SELL on RSI=77.1 (real overbought reading) while ATR and Trend Detection voted BUY — a genuinely mixed, non-scripted ensemble. |
| Fusion math verified by hand | SELL weight = 1.0 + 1.0 = 2.0, HOLD weight = 6 × 0.1 = 0.6, total = 2.6 → SELL confidence = 2.0/2.6 = 0.769, rounds to the 0.77 the API actually returned. Confirmed the algorithm, not just its output. |
| Individual results stored separately from the fused decision | `GET /decisions/{id}/strategies` returned exactly 8 rows per fused decision, independently queryable by `decision_id`, distinct from the `decisions` table row for the fused outcome itself. |
| Displayed in AI Center | Current AI Recommendation card showed the real fused SELL, 67% confidence, "Risk Level MEDIUM", and the full fusion reasoning string. Strategy Engine Breakdown table rendered all 8 real rows with distinct signals/confidences/reasoning text, visually confirmed via screenshot. Decision History showed multiple symbols (MSFT/GOOGL/AAPL) with `strategy: decision_fusion` and varying real signals. |
| No auto-execution (still holds) | After 270+ fused decisions (2,160+ individual strategy results) recorded in one running session, Paper Trading still showed "No open positions", "No trades yet", and cash unchanged at exactly $100,000.00 — the vastly more active engine still never once calls `POST /orders/`. |
| No LLM / external AI | Grepped the diff for any HTTP client usage, API keys, or model-provider imports in the new code — none. Every strategy is closed-form pandas/numpy arithmetic over the local OHLCV buffer; `pyproject.toml` gained zero new dependencies this sprint. |
| Health check | `GET /health/` → `decisions_available: healthy` after the schema change (new `strategy_results` table alongside `decisions`), confirming the extended SQLite store still satisfies the pre-existing health check unchanged. |
| Regression sweep | Clicked through all six pages in both Live and Demo Mode after the rebuild — zero console errors. Demo Mode's new 8-row illustrative breakdown rendered correctly and confirmed to never call the real backend. |

## What was deliberately left alone

- **`MomentumStrategy` (Sprint 3)** — left in the codebase, unused by the live engine. Removing working code that isn't causing a problem wasn't asked for.
- **No UI to reconfigure which strategies run, or their weights** — the fusion is a fixed, equal-standing confidence-weighted vote across all 8; a configuration UI is a reasonable future sprint, not requested here.
- **No new StrategyType enum values** — the 8 new strategies reuse the existing `StrategyType` categories (`MEAN_REVERSION`, `TREND_FOLLOWING`, `BREAKOUT`, `STATISTICAL_ARBITRAGE`) rather than expanding the schema; each strategy's own `name` is what distinguishes it everywhere it matters (storage, API, UI).
- **ATR/Support-Resistance intrabar-range limitation** — not "fixed" by fabricating fake high/low spread, since that would mean displaying invented data. Documented honestly in-code and in `PROJECT_STATUS.md` instead; the formulas are already forward-compatible with real OHLC bars if the tick source ever provides them.
