# Sprint 1 Completion Report — Truthfulness & Production-Safety Pass

**Date:** 2026-09-03
**Scope:** P0 items from [`CTO-FUNCTIONAL-AUDIT-REPORT.md`](CTO-FUNCTIONAL-AUDIT-REPORT.md), extended per this sprint's explicit objectives: remove every fake `DEMO` leak from Live Mode, wire Dashboard/Trading/AI Center/Paper Trading widgets to real backend APIs, replace hardcoded placeholders with real data, and make Risk Status / Kill Switch truthful.
**Constraints honored:** no new features, no UI redesign — every change below either (a) calls an existing, already-working backend endpoint that the frontend previously ignored, or (b) adds a small, read-only field/endpoint that exposes data the backend already computes internally but never surfaced. No mock data, no bypass, no placeholder logic was added.

## What changed, file by file

| File | Change |
|---|---|
| `src/api/static/app.js` | Rewired `refreshDashboard`, `refreshTrading`, `refreshAI`, `refreshPaper`, `refreshHealth` to call real endpoints in Live Mode; fixed the three demo-data leaks; fixed the `renderEquity` NaN bug; fixed the paper-trading start payload contract bug. |
| `src/api/static/index.html` | Added `id="paper-config-symbols"` / `id="paper-config-tick"` to the existing Session Configuration card so real config values can be bound — no visual/layout change. |
| `src/api/routers/status.py` | Added `GET /status/risk` — a new, minimal, read-only endpoint exposing the real `KillSwitch` component's state and thresholds (state, drawdown %, daily loss %, consecutive losses, vs. configured limits). This data existed inside the running system already (`KillSwitch.get_status()`); it was simply never exposed over the API. |
| `src/api/routers/decisions.py` | Added `reasoning_summary`, `risk_failed_checks`, `risk_passed_checks` to the existing `GET /decisions/` response — these are fields already present on the internal `DecisionRecord`/`RiskAssessment` objects that were being computed but silently dropped before reaching the API response. |

## Widget-by-widget changelog

### Dashboard

| Widget | Before | After | Verified |
|---|---|---|---|
| Portfolio Value / Day P&L / Total P&L / Buying Power | Hardcoded `$0.00` in Live Mode | Real `GET /portfolio/` | Logged in as admin/admin on a clean cache partition: showed real `$100,000.00` cash/total value from the paper broker's actual account state, `$0.00` P&L (honest — no trades yet, no fabricated number). |
| Open Positions table | Always empty in Live Mode (never called backend) | Real `GET /portfolio/` positions | Confirmed "No open positions" (honest, matches real empty broker state) — network log shows `GET /portfolio/ → 200`. |
| Equity Curve | Flat 1-point line, **and threw a console error** (`NaN` in SVG `points`, a pre-existing bug in `renderEquity` never previously exercised since Dashboard never called real data before) | Real current portfolio value; fixed the div-by-zero in `renderEquity` for single-point series | Confirmed zero console errors across all six pages after the fix, on two separate clean-cache reloads. |
| Risk Status / Kill Switch / Max Drawdown / Daily Loss | Hardcoded `NORMAL` / `DISARMED` / `0.0%` always, regardless of real state | Real `GET /status/risk` | Confirmed live: shows **"NOT MONITORED"** / **"DISARMED"** / **0.0%** / **0.0%** — the true state, since the kill switch is never armed anywhere in the current system. This is a materially different (and more honest) signal than the old permanent "NORMAL." |
| AI Engine / Decisions Today / Avg Confidence | Hardcoded `ONLINE` / `6` / `82%` always | Real `GET /decisions/`, aggregated client-side (today's count, average confidence) | Confirmed live: `ONLINE` (endpoint reachable), `Decisions Today: 0`, `Avg Confidence: 0%` — honest, matches the real empty decision store. |
| Market status | Hardcoded `OPEN` badge, permanently | Real computation from current time in `America/New_York`, standard NYSE regular-session hours (Mon–Fri 9:30–16:00 ET) | Confirmed the badge switches between OPEN/CLOSED based on actual wall-clock time via `Intl.DateTimeFormat`. **Known limitation, documented in code:** does not account for market holidays. |
| Active Strategies | Empty in Live Mode already (no leak) | Unchanged — no strategies backend endpoint exists (tracked as a P2 item in the audit report, out of scope: would require a new registry, which is new-feature territory) | No change needed; confirmed still shows nothing fake. |

### Trading

| Widget | Before | After | Verified |
|---|---|---|---|
| Watchlist | Demo data only | No quotes/watchlist backend exists (P2 gap) — now shows an honest "No live quote feed configured" message instead of silently being empty | Confirmed via screenshot. |
| Orders tab | Demo data only in Live Mode | Real `GET /orders/` | Confirmed "No orders" (honest, real, matches empty order book) — network log shows `GET /orders/ → 200`. |
| Positions tab | Demo data only | Real `GET /portfolio/` | Confirmed empty/honest in a fresh system. |
| Closed tab | **Leaked `DEMO.closed` unconditionally, even with Demo Mode off** | Gated by `demoMode`; honest "No closed positions" in Live Mode (no realized-P&L history endpoint exists yet — P2 gap, documented) | Confirmed via direct DOM check: `closed-body` textContent = "No closed positions" with Demo Mode off. |
| AI Decisions panel | **Leaked `DEMO.decisions.slice(0,4)` unconditionally** | Gated by `demoMode`; real `GET /decisions/?limit=4` in Live Mode | Confirmed "No decisions" shown in Live Mode (honest, matches empty store). |
| Risk Panel | 100% static HTML, identical numbers regardless of mode | Real `GET /status/risk` in Live Mode, showing current/limit pairs | Confirmed live: "Max Drawdown 0.0% / 10.0%", "Daily Loss Limit 0.0% / 5.0%", "Consecutive Losses 0/5" — real current values against real configured limits, not the old static "10.0%" / "5.0%" / "0/5" that never changed. |
| BUY/SELL buttons | Not implemented, no handler | **Unchanged** — wiring these to `POST /orders/` requires a new order-entry form/modal (new UI surface), explicitly out of scope for "no new features, no redesign." Documented as deferred to a future sprint. | N/A — confirmed no regression (buttons render, still inert). |

### AI Center

| Widget | Before | After | Verified |
|---|---|---|---|
| Current Recommendation (signal/symbol/strategy/confidence) | Hardcoded fallback object in Live Mode | Real `GET /decisions/`, most recent record | Confirmed live: `symbol: -`, `signal: N/A` (honestly — no "signal"/action field exists anywhere in the decision data model, so it is shown as unavailable rather than guessed), `confidence: 0%`, matching the real empty decision store. |
| Analysis & Risk (reasoning, risk factors, target, stop) | Hardcoded demo text | Real `reasoning_summary` and `risk_failed_checks` (now exposed by the API, see decisions.py change) for reasoning/risk factors; `target_price`/`stop_loss` honestly shown as **N/A** since no such fields exist anywhere in the backend's decision model | Confirmed live: reasoning shows "No decisions recorded yet.", target/stop show "N/A" instead of a fabricated `$0.00`. |
| Decision History table | **Leaked `DEMO.decisions` unconditionally, even with Demo Mode off** | Gated by `demoMode`; real `GET /decisions/?limit=100` in Live Mode | Confirmed via direct DOM check with Demo Mode off: table shows "No decisions" (honest), not the 6 fake demo rows it showed before regardless of mode. Confirmed demo mode still correctly shows all 6 demo rows (regression check passed). |

### Paper Trading

| Widget | Before | After | Verified |
|---|---|---|---|
| Session Status / Initial Capital / Current Value / Trades Executed | Hardcoded fallback object, never called the real (already-working) status endpoint | Real `GET /execution/paper/status` | Confirmed end-to-end: started a real session (see below), stats updated to real `RUNNING` / `$100,000.00` capital / `$100,000.00` value; stopped it, confirmed reverted to `STOPPED` / real state. |
| Start Session button | Called the real endpoint, but **sent `{capital: 100000}` when the backend expects `initial_capital`** — silently ignored by FastAPI/Pydantic, only "worked" because the default happened to match | Fixed to send `initial_capital` | Confirmed via live test: started a session, backend `config.initial_capital` correctly reflected what was requested (previously any non-default value the user might have entered would have been silently discarded). |
| Pause button | No-op, no backend capability | **Unchanged** — `PaperTradingMode` has no pause capability server-side; adding one is new backend work, out of scope | Documented as a genuine capability gap in the audit report, not silently left broken. |
| Session Configuration card | 100% hardcoded ("AAPL, MSFT, GOOGL", "1.0s") regardless of what was actually running | Real `config.symbols` / `config.tick_interval` from `GET /execution/paper/status`; added the two missing element IDs needed to bind them | Confirmed live: after starting a session, the card showed the real "AAPL, MSFT, GOOGL" and "1s" pulled from the actual running session's config (not the hardcoded string — verified by checking they come from the API response, not the static HTML default). |
| Live Activity log | Fabricated 6-line canned trade log shown whenever a session was "active," regardless of what actually happened | Honest state: "No paper trading activity" when stopped, "Session running. Trade-by-trade activity feed is not yet available" when running (no real activity-feed endpoint exists — P2 gap, documented; the two real WebSocket endpoints exist server-side but wiring them in is out of scope for this sprint's "no new features" constraint) | Confirmed live during the start/stop test above: no fake trade lines appeared. |

### System Health

| Widget | Before | After | Verified |
|---|---|---|---|
| Service Status list | Called the real `GET /health/` endpoint, but **the frontend's key list (`api`, `database`, `redis`, `kafka`, `workers`) never matched the real response's key names (`metrics_available`, `alerts_available`, `audit_available`, `decisions_available`, `system_uptime`)** — every item always showed "UNKNOWN" regardless of true health. This was a genuine defect discovered during this sprint's manual verification, not present in the original audit's classification. | Fixed the key mapping to match the real backend response | Confirmed live: all five real checks now correctly show **HEALTHY** (matching the real `/health/` payload verified via direct `fetch`). |
| Performance Metrics chart | Hardcoded placeholder text, always | Real `GET /metrics/snapshot`, rendered as a simple counter/gauge list (no chart library added — stays within "no redesign") | Confirmed live: shows real `system.startup: 1`, `health.check: 7` counters instead of the static placeholder text; gauges with `null` values render as "—" rather than the literal word "null". |
| Memory Usage / CPU Usage / API Latency bars | Hardcoded (`128 MB / 4.0 GB (3.2%)`, `8.5%`, `12ms`) | **Unchanged** — the only backend diagnostics endpoints (`/diagnostics/memory`, `/diagnostics/system`) return garbage-collector counts, not real OS memory/CPU figures; producing real numbers would require adding `psutil` as a new dependency, which crosses into new-feature/new-dependency territory explicitly excluded from this sprint | Documented as an intentionally deferred, genuine backend gap (not silently left as a lie without explanation). |

### Reports

**Unchanged, entirely out of scope.** Confirmed via the original audit: zero `/report*` endpoints exist anywhere in the API. Wiring this page to anything real requires building a net-new report-generation backend capability — explicitly a new feature, explicitly excluded by this sprint's constraints. Left as-is rather than silently building something not asked for.

## How every change was verified

All verification was done against the actual running Docker stack (`docker compose up --build`), not by code inspection alone:

1. Rebuilt the container after each change.
2. Loaded the app in the Browser tool on a **fresh, never-before-used loopback address** (`127.0.0.1` → `127.0.0.2` → `127.0.0.3` across the three rebuild cycles) specifically to guarantee a real network fetch of the updated JS, not a stale browser-cached copy (the exact class of bug fixed in the prior authentication sprint).
3. Logged in as `admin`/`admin` for real, then clicked through **all six pages** (Dashboard, Trading, AI Center, Paper Trading, System Health, Reports) and inspected: rendered DOM content, `console` for JS errors, and the network log for the actual HTTP calls and their status codes.
4. Explicitly started and stopped a real paper trading session to verify the Start/Stop buttons and the payload-contract fix end-to-end.
5. Explicitly toggled Demo Mode on/off on every affected page to confirm (a) the three demo leaks are fixed in Live Mode and (b) Demo Mode itself is unaffected (regression check).
6. Found and fixed two defects that only surfaced during this manual verification (not caught by static review): the Dashboard equity-curve `NaN` console error, and the System Health key-name mismatch that made every service always show "UNKNOWN."

No console errors were present on any of the six pages, in either Live or Demo Mode, at the end of this sprint.

## What was deliberately left alone (and why)

- **Trading BUY/SELL buttons** — backend (`POST /orders/`) is real and ready, but wiring requires a new order-entry UI surface (new feature).
- **Paper Trading Pause** — no backend capability exists; adding one is backend feature work.
- **Reports page** — no backend exists at all; building one is a new feature.
- **Memory/CPU/API Latency bars** — no real-data source exists without a new dependency (`psutil`).
- **Watchlist / live quotes** — no market-data endpoint exists.
- **Equity time series, Active Strategies** — no history/strategy-registry endpoint exists.
- **"● Live" badge and WebSocket wiring** — real WebSocket endpoints exist server-side and are unused; connecting them is deferred (P3 in the audit).

All of the above were already identified as P1/P2/P3 items in the CTO Functional Audit Report and are intentionally out of scope for a P0-only, no-new-features sprint.
