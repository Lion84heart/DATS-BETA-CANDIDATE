"""Orders API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import UserRole, get_current_user, has_permission, record_audit
from api.dependencies import get_component
from trading.execution.broker_base import BrokerConnector
from trading.execution.orders import Order, OrderSide, OrderType

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreateRequest(BaseModel):
    """Request to create a new order."""

    symbol: str
    side: str = Field(..., pattern="^(?i)(buy|sell)$")
    order_type: str = Field(..., pattern="^(?i)(market|limit|stop|stop_limit)$")
    quantity: float = Field(..., gt=0)
    limit_price: float | None = None
    stop_price: float | None = None


class BatchOrderRequest(BaseModel):
    """Request to submit multiple orders."""

    orders: list[OrderCreateRequest]


@router.get("/")
async def list_orders(request: Request) -> dict:
    """List all orders. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
        # PaperBroker stores orders in _orders list
        if hasattr(broker, "_orders"):
            orders = broker._orders
            return {
                "count": len(orders),
                "orders": [
                    {
                        "order_id": o.order_id,
                        "symbol": o.symbol,
                        "side": o.side.name if hasattr(o.side, "name") else str(o.side),
                        "order_type": o.order_type.name if hasattr(o.order_type, "name") else str(o.order_type),
                        "quantity": o.quantity,
                        "filled_quantity": o.filled_quantity,
                        "status": o.status.name if hasattr(o.status, "name") else str(o.status),
                        "limit_price": o.limit_price,
                        "stop_price": o.stop_price,
                        "created_at": o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
                    }
                    for o in orders
                ],
            }
        return {"count": 0, "orders": [], "message": "Order history not available"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_order_history(
    request: Request,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get order history with filtering and pagination. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
        if not hasattr(broker, "_orders"):
            return {"count": 0, "orders": [], "total": 0, "offset": offset, "limit": limit}

        orders = list(broker._orders.values())
        # Filter by symbol
        if symbol:
            orders = [o for o in orders if o.symbol.upper() == symbol.upper()]
        # Filter by status
        if status:
            orders = [o for o in orders if str(o.status).upper() == status.upper()]

        total = len(orders)
        paginated = orders[offset:offset + limit]

        return {
            "count": len(paginated),
            "total": total,
            "offset": offset,
            "limit": limit,
            "orders": [
                {
                    "order_id": o.order_id,
                    "symbol": o.symbol,
                    "side": o.side.name if hasattr(o.side, "name") else str(o.side),
                    "order_type": o.order_type.name if hasattr(o.order_type, "name") else str(o.order_type),
                    "quantity": o.quantity,
                    "filled_quantity": o.filled_quantity,
                    "status": o.status.name if hasattr(o.status, "name") else str(o.status),
                    "limit_price": o.limit_price,
                    "stop_price": o.stop_price,
                    "created_at": o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
                }
                for o in paginated
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{order_id}")
async def get_order(order_id: str, request: Request) -> dict:
    """Get a specific order by ID. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        broker: BrokerConnector = get_component(request, "broker")
        if hasattr(broker, "_orders"):
            for o in broker._orders:
                if o.order_id == order_id:
                    return {
                        "order_id": o.order_id,
                        "symbol": o.symbol,
                        "side": o.side.name if hasattr(o.side, "name") else str(o.side),
                        "order_type": o.order_type.name if hasattr(o.order_type, "name") else str(o.order_type),
                        "quantity": o.quantity,
                        "filled_quantity": o.filled_quantity,
                        "status": o.status.name if hasattr(o.status, "name") else str(o.status),
                        "limit_price": o.limit_price,
                        "stop_price": o.stop_price,
                        "created_at": o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
                    }
        raise HTTPException(status_code=404, detail="Order not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_order(request: Request, order_req: OrderCreateRequest) -> dict:
    """Submit a new order. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        broker: BrokerConnector = get_component(request, "broker")

        # Risk validation: check kill switch
        kill_switch = get_component(request, "kill_switch")
        if kill_switch is not None and kill_switch.is_triggered:
            record_audit(current_user, "ORDER_REJECTED", "orders", "kill_switch_triggered")
            raise HTTPException(status_code=403, detail="Trading halted: kill switch is triggered")

        side = OrderSide.BUY if order_req.side.lower() == "buy" else OrderSide.SELL
        order_type = OrderType.MARKET
        if order_req.order_type.lower() == "limit":
            order_type = OrderType.LIMIT
        elif order_req.order_type.lower() == "stop":
            order_type = OrderType.STOP
        elif order_req.order_type.lower() == "stop_limit":
            order_type = OrderType.STOP_LIMIT

        order = Order(
            symbol=order_req.symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=order_req.quantity,
            limit_price=order_req.limit_price,
            stop_price=order_req.stop_price,
        )
        result = await broker.submit_order(order)

        # Audit log
        record_audit(
            current_user,
            "ORDER_CREATED",
            "orders",
            f"order_id={result.order_id}, symbol={order_req.symbol}, side={order_req.side}",
        )

        return {
            "order_id": result.order_id,
            "status": result.status,
            "filled_qty": result.filled_qty,
            "avg_fill_price": result.avg_fill_price,
            "commission": result.commission,
            "slippage_bps": result.slippage_bps,
            "message": result.message,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def create_batch_orders(request: Request, batch_req: BatchOrderRequest) -> dict:
    """Submit multiple orders in a batch. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        broker: BrokerConnector = get_component(request, "broker")

        # Risk validation: check kill switch
        kill_switch = get_component(request, "kill_switch")
        if kill_switch is not None and kill_switch.is_triggered:
            record_audit(current_user, "BATCH_ORDER_REJECTED", "orders", "kill_switch_triggered")
            raise HTTPException(status_code=403, detail="Trading halted: kill switch is triggered")

        results = []
        errors = []

        for order_req in batch_req.orders:
            try:
                side = OrderSide.BUY if order_req.side.lower() == "buy" else OrderSide.SELL
                order_type = OrderType.MARKET
                if order_req.order_type.lower() == "limit":
                    order_type = OrderType.LIMIT
                elif order_req.order_type.lower() == "stop":
                    order_type = OrderType.STOP
                elif order_req.order_type.lower() == "stop_limit":
                    order_type = OrderType.STOP_LIMIT

                order = Order(
                    symbol=order_req.symbol.upper(),
                    side=side,
                    order_type=order_type,
                    quantity=order_req.quantity,
                    limit_price=order_req.limit_price,
                    stop_price=order_req.stop_price,
                )
                result = await broker.submit_order(order)
                results.append({
                    "order_id": result.order_id,
                    "status": result.status,
                    "symbol": order_req.symbol.upper(),
                    "side": order_req.side.upper(),
                    "filled_qty": result.filled_qty,
                    "avg_fill_price": result.avg_fill_price,
                })
            except Exception as e:
                errors.append({
                    "symbol": order_req.symbol,
                    "side": order_req.side,
                    "error": str(e),
                })

        # Audit log
        record_audit(
            current_user,
            "BATCH_ORDER_CREATED",
            "orders",
            f"submitted={len(results)}, failed={len(errors)}",
        )

        return {
            "submitted": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{order_id}")
async def cancel_order(order_id: str, request: Request) -> dict:
    """Cancel an order by ID. Operator+."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.OPERATOR):
        raise HTTPException(status_code=403, detail="Operator access required")
    try:
        broker: BrokerConnector = get_component(request, "broker")
        ok = await broker.cancel_order(order_id)
        if not ok:
            raise HTTPException(status_code=400, detail="Order could not be cancelled")

        # Audit log
        record_audit(current_user, "ORDER_CANCELLED", "orders", f"order_id={order_id}")

        return {"order_id": order_id, "status": "cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
