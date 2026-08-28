"""Tests for the ConnectorManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.market.base_connector import BaseDataConnector
from src.market.connector_manager import ConnectorManager
from src.market.jupiter_connector import JupiterConnector


class MockConnector(BaseDataConnector):
    """A mock connector for testing the manager."""

    def __init__(self, name: str = "mock") -> None:
        self._name = name
        self._connected = False
        self.health = {"status": "healthy"}

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def health_check(self) -> dict:
        return self.health


@pytest.fixture
def manager() -> ConnectorManager:
    return ConnectorManager()


class TestConnectorManagerRegistration:
    def test_register_connector(self, manager):
        conn = MockConnector("test")
        manager.register("test", conn)
        assert "test" in manager.list_connectors()

    def test_register_duplicate_raises(self, manager):
        conn = MockConnector("test")
        manager.register("test", conn)
        with pytest.raises(ValueError, match="already registered"):
            manager.register("test", MockConnector("test2"))

    def test_get_connector(self, manager):
        conn = MockConnector("test")
        manager.register("test", conn)
        retrieved = manager.get("test")
        assert retrieved is conn

    def test_get_missing_raises(self, manager):
        with pytest.raises(KeyError, match="not registered"):
            manager.get("missing")

    def test_unregister(self, manager):
        conn = MockConnector("test")
        manager.register("test", conn)
        manager.unregister("test")
        assert "test" not in manager.list_connectors()

    def test_unregister_missing_raises(self, manager):
        with pytest.raises(KeyError, match="not registered"):
            manager.unregister("missing")

    def test_list_connectors_empty(self, manager):
        assert manager.list_connectors() == []


class TestConnectorManagerLifecycle:
    @pytest.mark.asyncio
    async def test_connect_all(self, manager):
        conn1 = MockConnector("c1")
        conn2 = MockConnector("c2")
        manager.register("c1", conn1)
        manager.register("c2", conn2)

        await manager.connect_all()
        assert conn1.is_connected
        assert conn2.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_all(self, manager):
        conn1 = MockConnector("c1")
        manager.register("c1", conn1)
        await manager.connect_all()
        assert conn1.is_connected

        await manager.disconnect_all()
        assert not conn1.is_connected

    @pytest.mark.asyncio
    async def test_connect_all_empty(self, manager):
        await manager.connect_all()  # Should not raise

    @pytest.mark.asyncio
    async def test_disconnect_all_empty(self, manager):
        await manager.disconnect_all()  # Should not raise

    @pytest.mark.asyncio
    async def test_connect_all_partial_failure(self, manager):
        class FailingConnector(MockConnector):
            async def connect(self) -> None:
                raise ConnectionError("fail")

        conn1 = MockConnector("ok")
        conn2 = FailingConnector("fail")
        manager.register("ok", conn1)
        manager.register("fail", conn2)

        # Should not raise — logs error instead
        await manager.connect_all()
        assert conn1.is_connected
        assert not conn2.is_connected


class TestConnectorManagerHealth:
    @pytest.mark.asyncio
    async def test_health_all(self, manager):
        conn1 = MockConnector("c1")
        conn2 = MockConnector("c2")
        manager.register("c1", conn1)
        manager.register("c2", conn2)

        health = await manager.health_all()
        assert "c1" in health
        assert "c2" in health
        assert health["c1"]["status"] == "healthy"
        assert health["c2"]["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_all_empty(self, manager):
        health = await manager.health_all()
        assert health == {}

    @pytest.mark.asyncio
    async def test_health_all_with_failure(self, manager):
        class FailingHealthConnector(MockConnector):
            async def health_check(self) -> dict:
                raise RuntimeError("health check failed")

        conn1 = MockConnector("ok")
        conn2 = FailingHealthConnector("fail")
        manager.register("ok", conn1)
        manager.register("fail", conn2)

        health = await manager.health_all()
        assert health["ok"]["status"] == "healthy"
        assert health["fail"]["status"] == "unhealthy"
        assert "health check failed" in health["fail"]["error"]

    @pytest.mark.asyncio
    async def test_health_all_unhealthy_connector(self, manager):
        conn = MockConnector("sick")
        conn.health = {"status": "unhealthy", "error": "timeout"}
        manager.register("sick", conn)

        health = await manager.health_all()
        assert health["sick"]["status"] == "unhealthy"
