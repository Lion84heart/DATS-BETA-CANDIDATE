"""Execution control API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.auth import UserRole, get_current_user, get_user_from_token, has_permission, record_audit
from trading.execution.paper_trading import PaperTradingConfig, PaperTradingMode

router = APIRouter(prefix="/execution", tags=["execution"])


class PaperTradingStartRequest(BaseModel):
    """Request to start paper trading."""

    symbols: list[str] = ["AAPL"]
    initial_capital: float = 100000.0
    tick_interval: float = 1.0
    lookback: int = 20


@router.post("/paper/start")
async def start_paper_trading(
    request: Request,
    req: PaperTradingStartRequest | None = None,
) -> dict:
    """Start paper trading mode. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        if req is None:
            req = PaperTradingStartRequest()

        if hasattr(request.app.state, "paper_mode") and request.app.state.paper_mode is not None:
            if request.app.state.paper_mode._running:
                raise HTTPException(status_code=409, detail="Paper trading already running")

        config = PaperTradingConfig(
            symbols=req.symbols,
            initial_capital=req.initial_capital,
            tick_interval=req.tick_interval,
            lookback=req.lookback,
        )
        mode = PaperTradingMode(config)
        ok = await mode.start()
        if not ok:
            raise HTTPException(status_code=500, detail="Failed to start paper trading")

        request.app.state.paper_mode = mode

        # Audit log
        auth_header = request.headers.get("authorization", "")
        user = None
        if auth_header.startswith("Bearer "):
            user = get_user_from_token(auth_header[7:])
        record_audit(user, "PAPER_TRADING_START", "execution", f"symbols={req.symbols}, capital={req.initial_capital}")

        return {
            "status": "started",
            "symbols": req.symbols,
            "initial_capital": req.initial_capital,
            "tick_interval": req.tick_interval,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paper/stop")
async def stop_paper_trading(request: Request) -> dict:
    """Stop paper trading mode. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        mode: PaperTradingMode | None = getattr(request.app.state, "paper_mode", None)
        if mode is None or not mode._running:
            raise HTTPException(status_code=409, detail="Paper trading not running")

        await mode.stop()
        request.app.state.paper_mode = None

        # Audit log
        auth_header = request.headers.get("authorization", "")
        user = None
        if auth_header.startswith("Bearer "):
            user = get_user_from_token(auth_header[7:])
        record_audit(user, "PAPER_TRADING_STOP", "execution")

        return {"status": "stopped"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper/status")
async def get_paper_trading_status(request: Request) -> dict:
    """Get paper trading status. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        mode: PaperTradingMode | None = getattr(request.app.state, "paper_mode", None)
        if mode is None:
            return {"running": False, "message": "Paper trading not started"}
        return {
            "running": mode._running,
            "account": mode.get_account_summary(),
            "config": {
                "symbols": mode.config.symbols,
                "initial_capital": mode.config.initial_capital,
                "tick_interval": mode.config.tick_interval,
                "lookback": mode.config.lookback,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
