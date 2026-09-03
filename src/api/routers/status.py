"""System status API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth import get_current_user
from api.dependencies import get_component, get_lifecycle, get_registry
from system.lifecycle import SystemLifecycle

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/")
async def system_status(request: Request) -> dict:
    """Get overall system status."""
    lifecycle: SystemLifecycle = get_lifecycle(request)
    return {
        "state": lifecycle.state.name,
        "uptime_seconds": lifecycle.uptime_seconds,
        "is_running": lifecycle.is_running,
        "is_shutting_down": lifecycle.is_shutting_down,
    }


@router.get("/components")
async def component_status(request: Request) -> dict:
    """Get status of all registered components."""
    registry = get_registry(request)
    return {
        "components": registry.to_dict(),
        "count": len(registry.list_components()),
    }


@router.get("/risk")
async def risk_status(request: Request) -> dict:
    """Get real-time risk/kill-switch state for the dashboard.

    Exposes the actual KillSwitch component's state and thresholds —
    replaces the dashboard's previously hardcoded "NORMAL"/"DISARMED"
    display, which never reflected the real system state.
    """
    get_current_user(request)  # Any authenticated user
    try:
        kill_switch = get_component(request, "kill_switch")
        status_dict = kill_switch.get_status()

        current_value = None
        try:
            broker = get_component(request, "broker")
            current_value = broker.account.total_value
        except Exception:
            pass

        peak_value = status_dict["peak_value"]
        current_drawdown_pct = 0.0
        if peak_value and current_value is not None and peak_value > 0:
            current_drawdown_pct = max(0.0, (peak_value - current_value) / peak_value)

        daily_pnl = status_dict["daily_pnl"]
        daily_loss_pct = 0.0
        if daily_pnl < 0 and current_value:
            daily_loss_pct = abs(daily_pnl) / current_value

        return {
            "kill_switch_state": status_dict["state"],
            "current_drawdown_pct": current_drawdown_pct,
            "max_drawdown_limit_pct": status_dict["config"]["max_drawdown_pct"],
            "daily_loss_pct": daily_loss_pct,
            "daily_loss_limit_pct": status_dict["config"]["daily_loss_limit_pct"],
            "consecutive_losses": status_dict["consecutive_losses"],
            "consecutive_losses_limit": status_dict["config"]["consecutive_losses"],
            "events_triggered": status_dict["events_triggered"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transitions")
async def lifecycle_transitions(request: Request) -> dict:
    """Get lifecycle transition history."""
    lifecycle: SystemLifecycle = get_lifecycle(request)
    transitions = lifecycle.get_transitions()
    return {
        "transitions": [
            {
                "from": t.from_state.name,
                "to": t.to_state.name,
                "timestamp": t.timestamp,
                "reason": t.reason,
            }
            for t in transitions
        ],
        "count": len(transitions),
    }
