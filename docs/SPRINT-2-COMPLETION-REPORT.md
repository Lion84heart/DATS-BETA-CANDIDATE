# Sprint 2 Completion Report — Paper Trading Engine

**Date:** 2026-09-04
**Scope:** Make Paper Trading fully functional — real Buy/Sell, position management, real-time unrealized P&L, closing positions, trade history — connected end-to-end to the existing backend architecture.
**Constraints honored:** no fake/DEMO data, no real-money trading, no UI redesign, no crypto integration, existing architecture reused wherever possible.

## The core problem this sprint solved

The Paper Trading page's Start/Stop buttons previously created a **separate, disconnected `PaperTradingMode` instance with its own private `PaperBroker`**, entirely unrelated to the `broker` component that Dashboard, Trading, and Portfolio already read from. There was no Buy/Sell UI anywhere, and even if there had been, the registered `broker` component had **never received a single price tick** — `PaperBroker.submit_order()` rejects any order for a symbol with no price data, so manual trading was structurally impossible against the real, shared account. Two further backend defects made this worse: `PaperBroker.submit_order()` never populated its own `_orders` dict (declared but unused), so `GET /orders/` and `GET /orders/history` would always return empty even after real fills; and `GET /orders/{id}` iterated the `_orders` dict's keys instead of its values, which would have crashed on first use.

Sprint 2 fixed all of this using pieces that already existed in the codebase but had never been wired together.

## What was built

### Backend

**`src/trading/execution/paper_broker.py`** — `submit_order()` now:
- Assigns a real order ID and records every attempt — filled *and* rejected — in `self._orders`, using the existing `Order.with_fill()` / `dataclasses.replace()` immutable-update pattern already defined on the `Order` model (not a new pattern).
- Adds a sell-side guard: an order to sell more than the currently held quantity is rejected (`"Cannot sell X: only Y held"`) — paper trading has no shorting.
- Stores `avg_fill_price` (via the existing `with_fill()` metadata) and `commission` (added to the same metadata dict) so trade history can show real fill economics.

**`src/api/routers/orders.py`** — Fixed two pre-existing bugs discovered while wiring this up:
- `list_orders` (`GET /orders/`) iterated `broker._orders` (a dict) directly, i.e. its *keys*, not `.values()` — would have raised `AttributeError` the first time an order actually existed.
- `get_order` (`GET /orders/{id}`) had the same key-vs-value bug.
- `get_order_history` now sorts newest-first and both list endpoints now surface `avg_fill_price` / `commission` from order metadata.

**`src/api/routers/execution.py`** — Rewritten. "Start/Stop Session" no longer spins up a disconnected `PaperTradingMode`. It now:
- Registers a `SimulatedConnector` (existing class, already used elsewhere for exactly this purpose) on the existing `feed` (`FeedManager`) component.
- Seeds starting prices for a small fixed symbol universe (AAPL, MSFT, GOOGL, TSLA, NVDA, AMZN, META, AMD) — a simulation parameter for the price generator, the same role `SimulatedConnector`'s own built-in 100.0 default already plays for unlisted symbols, not data presented anywhere as a real quote.
- Forwards every tick to the same `broker.on_price_tick()` that Dashboard/Trading/Portfolio already read the results of, via `feed.add_callback()`.
- `GET /paper/status` now reports the feed's real running state and the real broker's account (`PaperBroker.to_dict()`, extended with `initial_capital`).
- Stopping only disconnects the feed (freezes prices); it does **not** reset cash or positions — a paper account persists like a real brokerage connection pausing, not like starting over.

### Frontend (`src/api/static/app.js`, `index.html`)

Within the existing Paper Trading screen's card layout (same CSS classes, same grid structure — no new visual language):
- **"Session Configuration"** card replaced with **"Place Order"**: a symbol dropdown populated *only* from the real running session's tradable symbols, a quantity field, and BUY/SELL buttons wired to `POST /orders/`. Disabled with a clear inline reason whenever there's no active session or Demo Mode is on (manual trading only ever touches the real backend, consistent with how Demo Mode already worked from Sprint 1).
- **"Live Activity"** card replaced with **"Open Positions"**: a real table from `GET /portfolio/`, each row with a **Close** button that submits a full-quantity sell.
- New **"Trade History"** card (same table styling used everywhere else in the app) listing every real order attempt from `GET /orders/history`, filled and rejected alike.
- "Trades Executed" stat now counts real *filled* orders, not raw attempts.

## Widget-by-widget verification

All verification was against the real running Docker stack, rebuilt after each change, loaded from a fresh never-before-cached loopback address each time to guarantee real network fetches (the same discipline established fixing the original stale-cache authentication bug).

| Action | Result |
|---|---|
| Start Session | `POST /execution/paper/start` → real symbols/tick_interval echoed back; order-entry symbol dropdown populates from the response; Buy/Sell enable. |
| Buy (AAPL, qty 10) | Filled at a real simulated price (`$181.60`, matching the seed + slippage); position appeared instantly; cash reduced by fill cost + $1 commission; confirmation message showed the real fill price. |
| Real-time P&L | After ~7 seconds of a running session (1s tick interval), the same position's market price and unrealized P&L updated with no user action — confirmed the price genuinely moves and flows through to the UI. |
| Close position | Sold the full held quantity at the current simulated price; position disappeared from Open Positions; realized P&L reflected correctly in cash/total value; Trade History showed both the BUY and SELL rows. |
| Sell without holding | `POST /orders/` correctly rejected: *"Cannot sell 5.0 MSFT: only 0.0 held"* — confirms no shorting is possible. |
| Buy before feed has ticked | Correctly rejected: *"No price data for TSLA"* — and this rejection itself was recorded and displayed in Trade History (status `REJECTED`, `-` for fill price), not swallowed. |
| Multi-symbol trading | Held AAPL and MSFT simultaneously; both showed independent, correct live P&L; closing both left "No open positions" and both trades in history. |
| Stop Session | Buy/Sell correctly disabled again (fixed a bug during testing where the button stayed enabled after stop because the feed's subscribed-symbol list isn't cleared on disconnect — the frontend now also checks the session's `running` flag). Positions/cash were **not** reset by stopping. |
| Cross-page consistency | Dashboard's Portfolio Value matched the Paper Trading page's Current Value exactly after trades — confirming the single shared broker, not two disconnected accounts. |
| Demo Mode regression | Toggled Demo Mode on: Buy/Sell correctly disabled with an explicit message; positions/history show demo-appropriate content, never a live call. Toggled back off: Live Mode fully functional again. |
| Full page sweep | Clicked through all six pages in both Live and Demo Mode after every rebuild — zero console errors throughout. |

## What was deliberately left alone

- **Trading page BUY/SELL buttons** — manual trading now lives on the Paper Trading page, which was this sprint's explicit scope; wiring the Trading page's buttons to the same order flow is a small, separate follow-up.
- **Pause** — still a no-op; no backend capability exists for it, and adding one is new backend feature work outside "use the existing architecture."
- **Real host CPU/memory, Reports backend, live market quotes, WebSocket wiring** — unchanged from Sprint 1's documented gaps; none of these were in this sprint's objectives.
- **Cryptocurrency exchange integration** — not touched, per explicit instruction.
- **Real-money trading** — structurally impossible: the only broker in the execution path is `PaperBroker` (`paper_mode=True`); no live-broker connector exists anywhere in the codebase.
