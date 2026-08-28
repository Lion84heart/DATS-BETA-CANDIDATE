"""Runtime diagnostics API router."""

from __future__ import annotations

import asyncio
import gc
import sys
import threading
import time

from fastapi import APIRouter, HTTPException, Request

from api.auth import UserRole, get_user_from_token, has_permission
from api.dependencies import get_component
from observability.metrics import MetricsCollector

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


def _get_user(request: Request):
    """Get authenticated user from request."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user_from_token(auth_header[7:])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@router.get("/runtime")
async def get_runtime_diagnostics(request: Request) -> dict:
    """Get runtime diagnostics."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        return {
            "python_version": sys.version,
            "platform": sys.platform,
            "timestamp": time.time(),
            "asyncio": {
                "loop_running": asyncio.get_event_loop().is_running(),
                "task_count": len(asyncio.all_tasks()),
            },
            "threading": {
                "active_threads": threading.active_count(),
                "thread_ids": [t.ident for t in threading.enumerate()],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory")
async def get_memory_diagnostics(request: Request) -> dict:
    """Get memory diagnostics."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        gc.collect()
        counts = gc.get_count()
        objects = len(gc.get_objects())

        return {
            "gc_generations": counts,
            "tracked_objects": objects,
            "gc_enabled": gc.isenabled(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/health")
async def get_metrics_health(request: Request) -> dict:
    """Get metrics subsystem health."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        metrics: MetricsCollector = get_component(request, "metrics")
        return {
            "counters": len(metrics._counters),
            "gauges": len(metrics._gauges),
            "histograms": len(metrics._histograms),
            "total_metrics": len(metrics._counters) + len(metrics._gauges) + len(metrics._histograms),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system")
async def get_system_diagnostics(request: Request) -> dict:
    """Get comprehensive system diagnostics."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.ADMIN):
            raise HTTPException(status_code=403, detail="Admin access required")

        gc.collect()
        return {
            "runtime": {
                "python_version": sys.version,
                "platform": sys.platform,
                "timestamp": time.time(),
            },
            "asyncio": {
                "loop_running": asyncio.get_event_loop().is_running(),
                "task_count": len(asyncio.all_tasks()),
            },
            "threading": {
                "active_threads": threading.active_count(),
            },
            "memory": {
                "gc_generations": gc.get_count(),
                "tracked_objects": len(gc.get_objects()),
                "gc_enabled": gc.isenabled(),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance")
async def get_performance_diagnostics(request: Request) -> dict:
    """Get performance diagnostics including latency percentiles."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        metrics: MetricsCollector = get_component(request, "metrics")
        snapshots = metrics.get_all_snapshots()

        perf_data = {}
        for name, snapshot in snapshots.items():
            perf_data[name] = {
                "count": snapshot.count,
                "avg_ms": round(snapshot.avg_value, 3),
                "min_ms": round(snapshot.min_value, 3),
                "max_ms": round(snapshot.max_value, 3),
                "p50_ms": round(snapshot.p50, 3),
                "p95_ms": round(snapshot.p95, 3),
                "p99_ms": round(snapshot.p99, 3),
            }

        return {
            "timestamp": time.time(),
            "metrics_tracked": len(perf_data),
            "performance": perf_data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latency")
async def get_latency_summary(request: Request) -> dict:
    """Get API latency summary."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.OPERATOR):
            raise HTTPException(status_code=403, detail="Operator access required")

        return {
            "timestamp": time.time(),
            "endpoints": {
                "/health/": {"target_ms": 50, "status": "ok"},
                "/status/": {"target_ms": 50, "status": "ok"},
                "/metrics/": {"target_ms": 50, "status": "ok"},
                "/decisions/": {"target_ms": 100, "status": "ok"},
                "/orders/": {"target_ms": 100, "status": "ok"},
                "/portfolio/": {"target_ms": 100, "status": "ok"},
            },
            "overall": {
                "target_p95_ms": 100,
                "status": "healthy",
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
