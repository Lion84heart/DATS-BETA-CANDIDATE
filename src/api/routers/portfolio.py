"""Portfolio API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth import get_current_user
from api.dependencies import get_component
from trading.execution.paper_broker import PaperBroker

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/")
async def get_portfolio(request: Request) -> dict:
    """Get full portfolio state."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: PaperBroker = get_component(request, "broker")
        positions = await broker.get_positions()
        return {
            "cash": broker.account.cash,
            "total_value": broker.account.total_value,
            "total_pnl": broker.account.total_pnl,
            "total_return_pct": broker.account.total_return_pct,
            "total_commission": broker.account.total_commission,
            "position_count": len(positions),
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_entry_price": p.avg_entry_price,
                    "market_price": p.market_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                }
                for p in positions
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions(request: Request) -> dict:
    """Get all positions."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: PaperBroker = get_component(request, "broker")
        positions = await broker.get_positions()
        return {
            "count": len(positions),
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_entry_price": p.avg_entry_price,
                    "market_price": p.market_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                }
                for p in positions
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_portfolio_summary(request: Request) -> dict:
    """Get portfolio summary."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: PaperBroker = get_component(request, "broker")
        return {
            "cash": broker.account.cash,
            "total_value": broker.account.total_value,
            "total_pnl": broker.account.total_pnl,
            "total_return_pct": broker.account.total_return_pct,
            "total_commission": broker.account.total_commission,
            "position_count": len(broker.account.positions),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
