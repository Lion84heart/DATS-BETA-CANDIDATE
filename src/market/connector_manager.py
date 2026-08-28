"""DATS — Connector Manager.

Central registry for managing multiple market-data connectors with
lifecycle and health-check orchestration.
"""

from __future__ import annotations

import logging
from typing import Any

from market.base_connector import BaseDataConnector

logger = logging.getLogger(__name__)


class ConnectorManager:
    """Registry and lifecycle manager for market-data connectors.

    Usage::

        mgr = ConnectorManager()
        mgr.register("jupiter", JupiterConnector())
        mgr.register("coingecko", CoinGeckoConnector())

        await mgr.connect_all()
        health = await mgr.health_all()
        await mgr.disconnect_all()
    """

    def __init__(self) -> None:
        self._connectors: dict[str, BaseDataConnector] = {}

    # -- Registration --------------------------------------------------------

    def register(self, name: str, connector: BaseDataConnector) -> None:
        """Register a connector under *name*.

        Args:
            name: Unique connector identifier.
            connector: ``BaseDataConnector`` instance.

        Raises:
            ValueError: If *name* is already registered.
        """
        if name in self._connectors:
            raise ValueError(f"Connector '{name}' is already registered.")
        self._connectors[name] = connector
        logger.info("Connector registered: %s (%s)", name, connector.name)

    def get(self, name: str) -> BaseDataConnector:
        """Retrieve a registered connector by *name*.

        Args:
            name: Connector identifier.

        Returns:
            The ``BaseDataConnector`` instance.

        Raises:
            KeyError: If *name* is not registered.
        """
        if name not in self._connectors:
            raise KeyError(f"Connector '{name}' is not registered.")
        return self._connectors[name]

    def list_connectors(self) -> list[str]:
        """Return a list of registered connector names."""
        return list(self._connectors.keys())

    def unregister(self, name: str) -> None:
        """Remove a connector from the registry.

        Args:
            name: Connector identifier.

        Raises:
            KeyError: If *name* is not registered.
        """
        if name not in self._connectors:
            raise KeyError(f"Connector '{name}' is not registered.")
        del self._connectors[name]
        logger.info("Connector unregistered: %s", name)

    # -- Lifecycle -----------------------------------------------------------

    async def connect_all(self) -> None:
        """Connect all registered connectors concurrently."""
        if not self._connectors:
            logger.warning("connect_all() called with no registered connectors.")
            return

        logger.info("Connecting all %d connector(s)...", len(self._connectors))
        import asyncio

        results = await asyncio.gather(
            *[c.connect() for c in self._connectors.values()],
            return_exceptions=True,
        )
        for (name, connector), result in zip(self._connectors.items(), results):
            if isinstance(result, Exception):
                logger.error("Connector '%s' failed to connect: %s", name, result)
            else:
                logger.info("Connector '%s' connected.", name)

    async def disconnect_all(self) -> None:
        """Disconnect all registered connectors concurrently."""
        if not self._connectors:
            return

        logger.info("Disconnecting all %d connector(s)...", len(self._connectors))
        import asyncio

        await asyncio.gather(
            *[c.disconnect() for c in self._connectors.values()],
            return_exceptions=True,
        )
        logger.info("All connectors disconnected.")

    # -- Health --------------------------------------------------------------

    async def health_all(self) -> dict[str, dict[str, Any]]:
        """Run health checks on all registered connectors concurrently.

        Returns:
            Mapping of connector name → health-check dict.
        """
        if not self._connectors:
            return {}

        import asyncio

        results = await asyncio.gather(
            *[c.health_check() for c in self._connectors.values()],
            return_exceptions=True,
        )
        health: dict[str, dict[str, Any]] = {}
        for (name, _), result in zip(self._connectors.items(), results):
            if isinstance(result, Exception):
                health[name] = {"status": "unhealthy", "error": str(result)}
            else:
                health[name] = result
        return health
