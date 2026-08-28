"""Component registry for dependency injection and lifecycle management.

Provides a type-safe registry for all system components with
registration, retrieval, and dependency resolution.
"""

from __future__ import annotations

import logging
from typing import Any, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """Registry for system components with type-safe access.

    All major subsystems (data, strategy, risk, execution, monitoring,
    security, intelligence) register themselves here for dependency
    resolution and lifecycle management.
    """

    def __init__(self):
        self._components: dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        """Register a named component.

        Args:
            name: Unique component name.
            component: Component instance.
        """
        if name in self._components:
            logger.warning("Component '%s' already registered; overwriting", name)
        self._components[name] = component
        logger.info("Component registered: %s", name)

    def get(self, name: str, expected_type: type[T] | None = None) -> T:
        """Retrieve a component by name.

        Args:
            name: Component name.
            expected_type: Optional type for runtime checking.

        Returns:
            The component instance.

        Raises:
            KeyError: If component not registered.
            TypeError: If component type mismatch.
        """
        if name not in self._components:
            raise KeyError(f"Component '{name}' not registered")
        component = self._components[name]
        if expected_type is not None and not isinstance(component, expected_type):
            raise TypeError(
                f"Component '{name}' expected {expected_type.__name__}, "
                f"got {type(component).__name__}"
            )
        return component

    def has(self, name: str) -> bool:
        """Check if component is registered."""
        return name in self._components

    def remove(self, name: str) -> None:
        """Remove a component."""
        if name in self._components:
            del self._components[name]
            logger.info("Component removed: %s", name)

    def list_components(self) -> list[str]:
        """List all registered component names."""
        return list(self._components.keys())

    def clear(self) -> None:
        """Clear all registered components."""
        self._components.clear()
        logger.info("Component registry cleared")

    def to_dict(self) -> dict[str, str]:
        """Export registry contents as {name: type} map."""
        return {name: type(comp).__name__ for name, comp in self._components.items()}
