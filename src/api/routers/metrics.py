"""Metrics API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from api.dependencies import get_component
from observability.metrics import MetricsCollector

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/")
async def get_all_metrics(request: Request) -> dict:
    """Get all collected metrics."""
    try:
        metrics: MetricsCollector = get_component(request, "metrics")
        snapshots = metrics.get_all_snapshots()
        return {
            "counters": {name: metrics.get_counter(name) for name in snapshots.keys()},
            "gauges": {name: metrics.get_gauge(name) for name in snapshots.keys()},
            "snapshots": {
                name: {
                    "count": s.count,
                    "min": s.min_value,
                    "max": s.max_value,
                    "avg": s.avg_value,
                    "p50": s.p50,
                    "p95": s.p95,
                    "p99": s.p99,
                }
                for name, s in snapshots.items()
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/counter/{name}")
async def get_counter(name: str, request: Request) -> dict:
    """Get a specific counter."""
    try:
        metrics: MetricsCollector = get_component(request, "metrics")
        value = metrics.get_counter(name)
        return {"name": name, "value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gauge/{name}")
async def get_gauge(name: str, request: Request) -> dict:
    """Get a specific gauge."""
    try:
        metrics: MetricsCollector = get_component(request, "metrics")
        value = metrics.get_gauge(name)
        return {"name": name, "value": value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot")
async def get_metrics_snapshot(request: Request) -> dict:
    """Get metrics snapshot with percentiles."""
    try:
        metrics: MetricsCollector = get_component(request, "metrics")
        snapshots = metrics.get_all_snapshots()
        return {
            "counters": {name: metrics.get_counter(name) for name in snapshots.keys()},
            "gauges": {name: metrics.get_gauge(name) for name in snapshots.keys()},
            "histogram_stats": {
                name: {
                    "count": s.count,
                    "min": s.min_value,
                    "max": s.max_value,
                    "avg": s.avg_value,
                    "p50": s.p50,
                    "p95": s.p95,
                    "p99": s.p99,
                }
                for name, s in snapshots.items()
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(request: Request) -> str:
    """Export metrics in Prometheus exposition format."""
    try:
        metrics: MetricsCollector = get_component(request, "metrics")
        lines = []
        lines.append("# DATS Platform Metrics")
        lines.append(f"# Generated at {__import__('time').time()}")
        lines.append("")

        # Counters
        for name, value in metrics._counters.items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE dats_counter_{safe_name} counter")
            lines.append(f"dats_counter_{safe_name} {value}")

        # Gauges
        for name, value in metrics._gauges.items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE dats_gauge_{safe_name} gauge")
            lines.append(f"dats_gauge_{safe_name} {value}")

        # Histograms
        for name, snapshot in metrics.get_all_snapshots().items():
            safe_name = name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE dats_histogram_{safe_name} summary")
            lines.append(f"dats_histogram_{safe_name}_count {snapshot.count}")
            lines.append(f"dats_histogram_{safe_name}_sum {snapshot.count * snapshot.avg_value}")
            lines.append(f"dats_histogram_{safe_name}_avg {snapshot.avg_value}")
            lines.append(f"dats_histogram_{safe_name}_p50 {snapshot.p50}")
            lines.append(f"dats_histogram_{safe_name}_p95 {snapshot.p95}")
            lines.append(f"dats_histogram_{safe_name}_p99 {snapshot.p99}")

        return "\n".join(lines)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
