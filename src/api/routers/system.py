"""System control API router."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from api.auth import UserRole, get_user_from_token, has_permission, record_audit

router = APIRouter(prefix="/system", tags=["system"])


def _get_user(request: Request):
    """Get authenticated user from request."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user_from_token(auth_header[7:])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@router.post("/shutdown")
async def system_shutdown(request: Request) -> dict:
    """Initiate graceful system shutdown. Admin only."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.ADMIN):
            raise HTTPException(status_code=403, detail="Admin access required")

        lifecycle = request.app.state.lifecycle
        if lifecycle:
            await lifecycle.stop()

        # Audit log
        record_audit(current_user, "SYSTEM_SHUTDOWN", "system")

        return {
            "status": "shutdown_initiated",
            "timestamp": time.time(),
            "message": "System shutdown initiated. All services stopping.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state")
async def get_system_state(request: Request) -> dict:
    """Get current system state. Operator+."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        lifecycle = request.app.state.lifecycle
        registry = request.app.state.registry

        return {
            "state": getattr(lifecycle, "state", "UNKNOWN"),
            "is_running": getattr(lifecycle, "is_running", False),
            "timestamp": time.time(),
            "components": list(registry._components.keys()) if hasattr(registry, "_components") else [],
            "uptime_seconds": getattr(lifecycle, "uptime_seconds", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/version")
async def get_system_version(request: Request) -> dict:
    """Get system version information."""
    return {
        "version": "1.0.0-alpha-rc",
        "release": "Alpha Release Candidate",
        "sprint": "S17+",
        "build_date": "2026-08-08",
        "api_version": "v1",
    }


@router.get("/capabilities")
async def get_system_capabilities(request: Request) -> dict:
    """Get system capability summary."""
    return {
        "total_capabilities": 32,
        "validated_capabilities": 32,
        "alpha_readiness": "100%",
        "features": [
            "paper_trading",
            "websocket_feeds",
            "prometheus_export",
            "csv_export",
            "auth_rbac",
            "audit_logging",
            "rate_limiting",
            "runtime_diagnostics",
            "decision_review",
            "operator_dashboard",
            "batch_orders",
            "config_validation",
            "system_control",
            "audit_export",
            "order_history",
        ],
    }
