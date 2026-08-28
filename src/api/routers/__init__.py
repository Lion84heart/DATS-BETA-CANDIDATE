"""API routers package."""

from api.routers.audit import router as audit_router
from api.routers.auth import router as auth_router
from api.routers.config import router as config_router
from api.routers.decisions import router as decisions_router
from api.routers.diagnostics import router as diagnostics_router
from api.routers.execution import router as execution_router
from api.routers.health import router as health_router
from api.routers.metrics import router as metrics_router
from api.routers.orders import router as orders_router
from api.routers.portfolio import router as portfolio_router
from api.routers.positions import router as positions_router
from api.routers.status import router as status_router
from api.routers.system import router as system_router
from api.routers.websocket import router as websocket_router

__all__ = [
    "auth_router",
    "health_router",
    "status_router",
    "config_router",
    "portfolio_router",
    "positions_router",
    "orders_router",
    "decisions_router",
    "execution_router",
    "metrics_router",
    "audit_router",
    "diagnostics_router",
    "system_router",
    "websocket_router",
]
