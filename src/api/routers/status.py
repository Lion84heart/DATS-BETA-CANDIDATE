"""System status API router."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.dependencies import get_lifecycle, get_registry
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
