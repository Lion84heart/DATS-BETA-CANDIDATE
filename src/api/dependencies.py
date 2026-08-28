"""FastAPI dependencies for DATS API.

Provides dependency injection for system components
into API route handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from system.bootstrap import SystemBootstrap
from system.config_loader import ConfigLoader
from system.lifecycle import SystemLifecycle
from system.registry import ComponentRegistry


# Global fallback bootstrap for testing scenarios
_fallback_bootstrap: SystemBootstrap | None = None


def _ensure_bootstrap() -> SystemBootstrap:
    """Ensure bootstrap is available, creating if needed."""
    global _fallback_bootstrap
    if _fallback_bootstrap is None:
        _fallback_bootstrap = SystemBootstrap()
        result = _fallback_bootstrap.bootstrap()
        if not result.success:
            raise RuntimeError(f"Bootstrap failed: {result.errors}")
    return _fallback_bootstrap


def get_registry(request: Request) -> ComponentRegistry:
    """Get component registry from app state.

    Args:
        request: FastAPI request.

    Returns:
        ComponentRegistry.
    """
    if hasattr(request.app.state, "registry"):
        return request.app.state.registry
    return _ensure_bootstrap().registry


def get_lifecycle(request: Request) -> SystemLifecycle:
    """Get system lifecycle from app state.

    Args:
        request: FastAPI request.

    Returns:
        SystemLifecycle.
    """
    if hasattr(request.app.state, "lifecycle"):
        return request.app.state.lifecycle
    return _ensure_bootstrap().lifecycle


def get_config(request: Request) -> ConfigLoader:
    """Get config loader from app state.

    Args:
        request: FastAPI request.

    Returns:
        ConfigLoader.
    """
    if hasattr(request.app.state, "config"):
        return request.app.state.config
    return _ensure_bootstrap().config


def get_component(request: Request, name: str) -> Any:
    """Get a named component from registry.

    Args:
        request: FastAPI request.
        name: Component name.

    Returns:
        Component instance.
    """
    registry = get_registry(request)
    return registry.get(name)
