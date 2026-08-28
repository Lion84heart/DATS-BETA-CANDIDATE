"""DATS — Abstract Base Data Connector.

Defines the interface that all market-data connectors must implement.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class BaseDataConnector(ABC):
    """Abstract base class for all market-data connectors.

    Attributes:
        name: Human-readable connector identifier.
        is_connected: Whether the connector is currently connected.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the connector name."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Return ``True`` if the connector is connected."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish the connection to the external data source."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully tear down the connection."""

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return a health-check dictionary.

        Returns:
            Dict with at least a ``status`` key (``"healthy"`` or
            ``"unhealthy"``) and optional ``latency_ms``, ``error`` keys.
        """
