"""WebSocket endpoint for real-time platform updates.

Provides live feeds for:
- Decision stream (new decisions as they are recorded)
- Market data ticks
- System health changes
- Paper trading account updates
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth import get_user_from_token
from api.dependencies import get_component
from intelligence.decisions import DecisionStore
from observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])

# Active WebSocket connections
_connections: set[WebSocket] = set()


async def broadcast(message: dict[str, Any]) -> None:
    """Broadcast a message to all connected WebSocket clients."""
    dead = set()
    for ws in _connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _connections.discard(ws)


@router.websocket("/decisions")
async def decisions_websocket(websocket: WebSocket) -> None:
    """WebSocket stream for real-time decision updates."""
    await websocket.accept()

    # Authenticate via query param token
    token = websocket.query_params.get("token", "")
    user = get_user_from_token(token) if token else None
    if not user:
        await websocket.close(code=1008, reason="Authentication required")
        return

    _connections.add(websocket)
    logger.info("WebSocket client connected: %s", user.username)

    try:
        # Send initial decision count
        try:
            store: DecisionStore = get_component(websocket, "decision_store")
            records = store.query(limit=1)
            await websocket.send_json({
                "type": "connected",
                "user": user.username,
                "role": user.role.value,
                "message": "Decision stream active",
            })
        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })

        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action", "")
                if action == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": msg.get("timestamp")})
                elif action == "subscribe":
                    await websocket.send_json({"type": "subscribed", "channel": msg.get("channel", "decisions")})
                else:
                    await websocket.send_json({"type": "ack", "action": action})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", user.username)
    finally:
        _connections.discard(websocket)


@router.websocket("/market")
async def market_websocket(websocket: WebSocket) -> None:
    """WebSocket stream for real-time market data ticks."""
    await websocket.accept()

    token = websocket.query_params.get("token", "")
    user = get_user_from_token(token) if token else None
    if not user:
        await websocket.close(code=1008, reason="Authentication required")
        return

    _connections.add(websocket)
    logger.info("Market WebSocket client connected: %s", user.username)

    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "market",
            "message": "Market data stream active",
        })

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({"type": "ack", "action": msg.get("action")})
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        logger.info("Market WebSocket client disconnected: %s", user.username)
    finally:
        _connections.discard(websocket)


@router.websocket("/system")
async def system_websocket(websocket: WebSocket) -> None:
    """WebSocket stream for system health and metrics updates."""
    await websocket.accept()

    token = websocket.query_params.get("token", "")
    user = get_user_from_token(token) if token else None
    if not user:
        await websocket.close(code=1008, reason="Authentication required")
        return

    _connections.add(websocket)
    logger.info("System WebSocket client connected: %s", user.username)

    try:
        await websocket.send_json({
            "type": "connected",
            "channel": "system",
            "message": "System stream active",
        })

        # Send periodic health updates
        while True:
            try:
                metrics: MetricsCollector = get_component(websocket, "metrics")
                await websocket.send_json({
                    "type": "metrics",
                    "counters": dict(metrics._counters),
                    "gauges": dict(metrics._gauges),
                    "timestamp": asyncio.get_event_loop().time(),
                })
            except Exception as e:
                await websocket.send_json({"type": "error", "message": str(e)})

            # Wait for client message or timeout
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                try:
                    msg = json.loads(data)
                    if msg.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        logger.info("System WebSocket client disconnected: %s", user.username)
    finally:
        _connections.discard(websocket)
