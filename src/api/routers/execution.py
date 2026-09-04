"""Execution control API router.

Controls the simulated price feed that drives the paper trading
broker. "Starting" a paper trading session subscribes a set of
symbols on a simulated market data connector and starts streaming
ticks into the same ``broker`` component used by /orders, /portfolio
and /positions — there is a single, shared paper account, not a
separate one per session. This keeps every widget (Dashboard, Trading,
Paper Trading) reading a consistent, real state instead of two
disconnected broker instances.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.auth import UserRole, get_current_user, get_user_from_token, has_permission, record_audit
from api.dependencies import get_component
from market.connectors.simulated import SimulatedConnector
from market.feed import FeedManager
from trading.execution.paper_broker import PaperBroker

router = APIRouter(prefix="/execution", tags=["execution"])

# Starting prices for the simulated connector when a symbol is traded for
# the first time. This is a simulation parameter for the paper-trading price
# generator (same role as SimulatedConnector's own built-in 100.0 default for
# unlisted symbols) — not data displayed anywhere as if it were a live quote.
_DEFAULT_SEED_PRICES: dict[str, float] = {
    "AAPL": 182.50, "MSFT": 335.80, "GOOGL": 128.40, "TSLA": 255.30,
    "NVDA": 465.00, "AMZN": 158.00, "META": 510.00, "AMD": 142.00,
}


class PaperTradingStartRequest(BaseModel):
    """Request to start the simulated price feed for paper trading."""

    symbols: list[str] = ["AAPL", "MSFT", "GOOGL"]
    tick_interval: float = 1.0


@router.post("/paper/start")
async def start_paper_trading(
    request: Request,
    req: PaperTradingStartRequest | None = None,
) -> dict:
    """Start streaming simulated prices for the given symbols. Operator+.

    Fills the same ``broker`` component read by /orders, /portfolio, and
    /positions — so orders submitted after this call can actually fill
    (PaperBroker rejects orders for symbols with no price data), and
    open positions start receiving real-time unrealized P&L updates.
    """
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        if req is None:
            req = PaperTradingStartRequest()
        symbols = [s.upper() for s in req.symbols] or ["AAPL"]

        feed: FeedManager = get_component(request, "feed")
        broker: PaperBroker = get_component(request, "broker")

        if feed.get_state().active:
            raise HTTPException(status_code=409, detail="Paper trading feed already running")

        connector = SimulatedConnector(tick_interval=req.tick_interval)
        for symbol in symbols:
            connector.configure_symbol(symbol, _DEFAULT_SEED_PRICES.get(symbol, 100.0))

        feed.register_connector(connector, primary=True)
        if hasattr(broker, "on_price_tick") and broker.on_price_tick not in feed._callbacks:
            feed.add_callback(broker.on_price_tick)

        # AI Decision Engine — analyzes the same live tick stream and
        # records a BUY/SELL/HOLD recommendation for every pass. Advisory
        # only: it never submits an order (see intelligence/engine.py).
        ai_engine = getattr(request.app.state, "ai_engine", None)
        if ai_engine is not None and ai_engine.on_price_tick not in feed._callbacks:
            feed.add_callback(ai_engine.on_price_tick)

        ok = await feed.connect()
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to start simulated price feed")
        await feed.subscribe(symbols)

        request.app.state.paper_symbols = symbols
        request.app.state.paper_tick_interval = req.tick_interval

        auth_header = request.headers.get("authorization", "")
        user = get_user_from_token(auth_header[7:]) if auth_header.startswith("Bearer ") else None
        record_audit(user, "PAPER_TRADING_START", "execution", f"symbols={symbols}")

        return {"status": "started", "symbols": symbols, "tick_interval": req.tick_interval}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paper/stop")
async def stop_paper_trading(request: Request) -> dict:
    """Stop the simulated price feed. Operator+.

    Leaves the broker's cash/positions exactly as they are — stopping
    only freezes price movement, it does not reset the paper account.
    """
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        feed: FeedManager = get_component(request, "feed")
        if not feed.get_state().active:
            raise HTTPException(status_code=409, detail="Paper trading feed not running")

        await feed.disconnect()
        request.app.state.paper_symbols = []

        auth_header = request.headers.get("authorization", "")
        user = get_user_from_token(auth_header[7:]) if auth_header.startswith("Bearer ") else None
        record_audit(user, "PAPER_TRADING_STOP", "execution")

        return {"status": "stopped"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/status")
async def get_paper_trading_status(request: Request) -> dict:
    """Get the simulated feed's running state and the real account. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        feed: FeedManager = get_component(request, "feed")
        broker: PaperBroker = get_component(request, "broker")
        state = feed.get_state()
        ai_engine = getattr(request.app.state, "ai_engine", None)
        return {
            "running": state.active,
            "symbols": state.symbols,
            "tick_interval": getattr(request.app.state, "paper_tick_interval", None),
            "account": broker.to_dict(),
            "ai_engine": ai_engine.summary() if ai_engine is not None else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
