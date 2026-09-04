"""DATS Platform API — FastAPI application.

Production-grade API exposing operational endpoints for the
institutional AI trading platform.

Endpoints:
    /auth — Authentication (login, logout, me, sessions)
    /health — System health checks
    /status — System status and lifecycle
    /config — Configuration inspection and validation
    /portfolio — Portfolio state and positions
    /positions — Position details and summary
    /orders — Order submission, cancellation, history
    /decisions — Decision review, export, pipeline
    /execution — Execution control (paper trading)
    /metrics — Metrics and observability
    /audit — Audit history and summary
    /diagnostics — Runtime diagnostics (memory, threads, asyncio)
    /dashboard — Decision review dashboard (HTML)
    /operator — Unified operator interface (HTML)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.routers import (
    audit,
    auth,
    config,
    decisions,
    diagnostics,
    execution,
    health,
    metrics,
    orders,
    portfolio,
    positions,
    status,
    system,
    websocket,
)
from intelligence.engine import AIDecisionEngine
from system.bootstrap import SystemBootstrap
from system.config_loader import ConfigLoader
from system.decision_pipeline import DecisionPipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

# Base directory for resolving static files across environments
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STATIC_DIR = os.path.join(_BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — bootstrap on startup, cleanup on shutdown."""
    # Startup
    logger.info("DATS API starting up...")
    config_loader = ConfigLoader()
    bootstrap = SystemBootstrap(config_loader=config_loader)
    result = bootstrap.bootstrap()

    if not result.success:
        logger.error("Bootstrap failed: %s", result.errors)
        raise RuntimeError(f"Bootstrap failed: {result.errors}")

    # Store in app state
    app.state.bootstrap = bootstrap
    app.state.registry = result.registry
    app.state.lifecycle = result.lifecycle
    app.state.config = config_loader
    app.state.paper_mode = None

    # Initialize decision pipeline and the AI decision engine that feeds it
    try:
        store = result.registry.get("decision_store")
        pipeline = DecisionPipeline(store=store)
        app.state.pipeline = pipeline
        app.state.ai_engine = AIDecisionEngine(pipeline=pipeline)
    except Exception:
        app.state.pipeline = None
        app.state.ai_engine = None

    # Start lifecycle
    startup_ok = await result.lifecycle.start()
    if not startup_ok:
        logger.error("Lifecycle startup failed")
        raise RuntimeError("Lifecycle startup failed")

    logger.info("DATS API ready")
    yield

    # Shutdown
    logger.info("DATS API shutting down...")
    await result.lifecycle.stop()
    logger.info("DATS API stopped")


# Create FastAPI app
app = FastAPI(
    title="DATS Platform API",
    description="Institutional AI Trading Platform",
    version="1.0.0-beta",
    lifespan=lifespan,
)

# CORS — configurable via environment; default to restricted in production
_cors_origins = os.environ.get("CORS_ALLOW_ORIGINS", "")
if _cors_origins:
    allow_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()]
else:
    # Default: localhost only for safety
    allow_origins = ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(health.router)
app.include_router(status.router)
app.include_router(config.router)
app.include_router(portfolio.router)
app.include_router(positions.router)
app.include_router(orders.router)
app.include_router(decisions.router)
app.include_router(execution.router)
app.include_router(metrics.router)
app.include_router(audit.router)
app.include_router(diagnostics.router)
app.include_router(system.router)
app.include_router(websocket.router)

class _RevalidateStaticFiles(StaticFiles):
    """StaticFiles that forces revalidation on every request.

    The dashboard's HTML/CSS/JS are unversioned and change between deploys.
    Without an explicit directive, browsers apply heuristic freshness to
    Last-Modified and can keep serving a stale ``app.js`` for a long time
    after a new version is deployed, with no error to signal the mismatch.
    ``no-cache`` keeps the browser cache (cheap 304s via the ETag Starlette
    already sets) but requires a conditional GET before reuse, so a new
    deploy is always picked up on next load.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Static files for dashboard
try:
    app.mount("/static", _RevalidateStaticFiles(directory=_STATIC_DIR), name="static")
    logger.info("Static files mounted at /static from %s", _STATIC_DIR)
except Exception as e:
    logger.error("Failed to mount static files from %s: %s", _STATIC_DIR, e)


@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    """Platform entry point — serves the main SPA."""
    try:
        with open(os.path.join(_STATIC_DIR, "index.html"), "r") as f:
            return f.read()
    except FileNotFoundError:
        return """<!DOCTYPE html>
<html><head><title>DATS Platform</title></head>
<body style="background:#0a0e1a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px">
<h1>DATS Platform</h1><p>Frontend not built yet. Run setup to build the UI.</p></body></html>"""


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Decision review dashboard v2."""
    try:
        with open(os.path.join(_STATIC_DIR, "dashboard-v2.html"), "r") as f:
            return f.read()
    except FileNotFoundError:
        return """<!DOCTYPE html>
<html><head><title>DATS Dashboard</title></head>
<body><h1>DATS Decision Review Dashboard v2</h1>
<p>Dashboard HTML file not found.</p></body></html>"""


@app.get("/app", response_class=HTMLResponse)
async def app_entry() -> str:
    """SPA entry point."""
    try:
        with open(os.path.join(_STATIC_DIR, "index.html"), "r") as f:
            return f.read()
    except FileNotFoundError:
        return """<!DOCTYPE html>
<html><head><title>DATS Platform</title></head>
<body style="background:#0a0e1a;color:#e2e8f0;font-family:sans-serif;text-align:center;padding:60px">
<h1>DATS Platform</h1><p>Frontend not built yet.</p></body></html>"""


@app.get("/operator", response_class=HTMLResponse)
async def operator_interface() -> str:
    """Unified operator interface."""
    try:
        with open(os.path.join(_STATIC_DIR, "operator.html"), "r") as f:
            return f.read()
    except FileNotFoundError:
        return """<!DOCTYPE html>
<html><head><title>DATS Operator</title></head>
<body><h1>DATS Operator Interface</h1>
<p>Operator HTML file not found. Place src/api/static/operator.html</p></body></html>"""


#app.get("/openapi.json")
#async def openapi_schema() -> dict:
#    """OpenAPI schema endpoint."""
#    return app.openapi()
