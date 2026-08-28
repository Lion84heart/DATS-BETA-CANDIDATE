"""Health check API router."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.dependencies import get_component
from observability.health import HealthCheck, HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def health_overall(request: Request) -> dict:
    """Get overall system health status."""
    try:
        health: HealthCheck = get_component(request, "health")
        result = await health.run()
        # ServiceHealth dataclass returned
        checks_dict = {}
        for r in result.checks:
            if isinstance(r, tuple):
                checks_dict[r[0] if len(r) > 0 else "unknown"] = {
                    "healthy": r[1] if len(r) > 1 else False,
                    "message": r[2] if len(r) > 2 else "",
                }
            else:
                checks_dict[r.name] = {
                    "healthy": r.status == HealthStatus.HEALTHY,
                    "message": r.message,
                }
        return {
            "status": result.overall_status.value,
            "checks": checks_dict,
            "timestamp": result.timestamp,
        }
    except Exception as e:
        return {"status": "UNKNOWN", "error": str(e)}


@router.get("/{check_name}")
async def health_check_detail(check_name: str, request: Request) -> dict:
    """Get specific health check status."""
    try:
        health: HealthCheck = get_component(request, "health")
        result = await health.run(check_name)
        # Find the specific check result
        check_result = None
        for r in result.checks:
            if hasattr(r, 'name') and r.name == check_name:
                check_result = r
                break
            elif isinstance(r, tuple) and len(r) >= 2:
                if r[0] == check_name:
                    check_result = r
                    break
        
        if check_result is None:
            return {"check": check_name, "healthy": False, "error": "Check not found"}
        
        if isinstance(check_result, tuple):
            return {
                "check": check_name,
                "healthy": check_result[0] if len(check_result) > 0 else False,
                "message": check_result[1] if len(check_result) > 1 else "",
            }
        
        return {
            "check": check_name,
            "healthy": check_result.status == HealthStatus.HEALTHY,
            "message": check_result.message,
        }
    except Exception as e:
        return {"check": check_name, "healthy": False, "error": str(e)}
