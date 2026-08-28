"""Configuration API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth import UserRole, get_current_user, has_permission, record_audit
from api.dependencies import get_config
from system.config_loader import ConfigLoader

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/")
async def get_full_config(request: Request) -> dict:
    """Get full system configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    return config.to_dict()


@router.get("/trading")
async def get_trading_config(request: Request) -> dict:
    """Get trading configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    return config.trading.__dict__


@router.get("/risk")
async def get_risk_config(request: Request) -> dict:
    """Get risk configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    return config.risk.__dict__


@router.get("/data")
async def get_data_config(request: Request) -> dict:
    """Get data configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    return config.data.__dict__


@router.get("/monitoring")
async def get_monitoring_config(request: Request) -> dict:
    """Get monitoring configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    return config.monitoring.__dict__


@router.get("/validate")
async def validate_config(request: Request) -> dict:
    """Validate current configuration. Viewer+."""
    get_current_user(request)  # Any authenticated user
    config: ConfigLoader = get_config(request)
    errors = config.validate()
    return {
        "valid": len(errors) == 0,
        "errors": [str(e) for e in errors],
        "error_count": len(errors),
    }


@router.get("/runtime")
async def get_runtime_config(request: Request) -> dict:
    """Get runtime configuration state including environment and overrides. Viewer+."""
    get_current_user(request)  # Any authenticated user
    try:
        config: ConfigLoader = get_config(request)
        return {
            "environment": getattr(config, "environment", "development"),
            "config_path": getattr(config, "config_path", "default"),
            "loaded_at": getattr(config, "loaded_at", None),
            "sections": list(config.to_dict().keys()),
            "validation": {
                "valid": len(config.validate()) == 0,
                "error_count": len(config.validate()),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_config(request: Request) -> dict:
    """Reload configuration from disk. Admin only."""
    current_user = get_current_user(request)
    if not has_permission(current_user, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        config: ConfigLoader = get_config(request)
        if hasattr(config, "reload"):
            config.reload()

        # Audit log
        record_audit(current_user, "CONFIG_RELOAD", "config")

        return {
            "reloaded": True,
            "timestamp": __import__("time").time(),
            "validation": {
                "valid": len(config.validate()) == 0,
                "error_count": len(config.validate()),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
