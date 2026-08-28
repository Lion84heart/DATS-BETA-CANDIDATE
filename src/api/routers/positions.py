"""Positions API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth import get_current_user
from api.dependencies import get_component
from trading.execution.broker_base import BrokerConnector

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/")
async def list_positions(request: Request) -> dict:
    """List all current positions."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
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
                    "market_value": p.quantity * p.market_price,
                }
                for p in positions
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{symbol}")
async def get_position(symbol: str, request: Request) -> dict:
    """Get a specific position by symbol."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
        positions = await broker.get_positions()
        for p in positions:
            if p.symbol.upper() == symbol.upper():
                return {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_entry_price": p.avg_entry_price,
                    "market_price": p.market_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl": p.realized_pnl,
                    "market_value": p.quantity * p.market_price,
                }
        raise HTTPException(status_code=404, detail=f"Position for {symbol} not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary/overview")
async def get_positions_summary(request: Request) -> dict:
    """Get aggregate position summary."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
        positions = await broker.get_positions()
        total_value = sum(p.quantity * p.market_price for p in positions)
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        total_realized = sum(p.realized_pnl for p in positions)
        long_count = sum(1 for p in positions if p.quantity > 0)
        short_count = sum(1 for p in positions if p.quantity < 0)
        return {
            "position_count": len(positions),
            "long_count": long_count,
            "short_count": short_count,
            "total_market_value": total_value,
            "total_unrealized_pnl": total_unrealized,
            "total_realized_pnl": total_realized,
            "total_pnl": total_unrealized + total_realized,
            "symbols": [p.symbol for p in positions],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
