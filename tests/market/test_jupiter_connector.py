"""Tests for the Jupiter API connector (mocked HTTP)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.market.jupiter_connector import JupiterConnector
from src.market.schemas import PriceTick


class TestJupiterConnectorLifecycle:
    @pytest.mark.asyncio
    async def test_connect(self, jupiter_connector):
        assert not jupiter_connector.is_connected
        await jupiter_connector.connect()
        assert jupiter_connector.is_connected
        assert jupiter_connector._client is not None

    @pytest.mark.asyncio
    async def test_disconnect(self, jupiter_connector):
        await jupiter_connector.connect()
        assert jupiter_connector.is_connected
        await jupiter_connector.disconnect()
        assert not jupiter_connector.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, jupiter_connector):
        await jupiter_connector.disconnect()
        assert not jupiter_connector.is_connected

    @pytest.mark.asyncio
    async def test_name_property(self, jupiter_connector):
        assert jupiter_connector.name == "jupiter"


class TestJupiterConnectorHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, jupiter_connector):
        health = await jupiter_connector.health_check()
        assert health["status"] == "unhealthy"
        assert "not connected" in health["error"]

    @pytest.mark.asyncio
    async def test_health_check_success(self, connected_jupiter):
        mock_response = MagicMock()
        mock_response.status_code = 200
        connected_jupiter._client.get = AsyncMock(return_value=mock_response)

        health = await connected_jupiter.health_check()
        assert health["status"] == "healthy"
        assert health["error"] is None
        assert "latency_ms" in health

    @pytest.mark.asyncio
    async def test_health_check_degraded(self, connected_jupiter):
        mock_response = MagicMock()
        mock_response.status_code = 500
        connected_jupiter._client.get = AsyncMock(return_value=mock_response)

        health = await connected_jupiter.health_check()
        assert health["status"] == "degraded"


class TestJupiterConnectorGetPrice:
    @pytest.mark.asyncio
    async def test_get_price_not_connected_raises(self, jupiter_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await jupiter_connector.get_price(["SOL"])

    @pytest.mark.asyncio
    async def test_get_price_empty_list(self, connected_jupiter):
        result = await connected_jupiter.get_price([])
        assert result == []

    @pytest.mark.asyncio
    async def test_get_price_success(self, connected_jupiter):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "data": {
                "So1111...": {
                    "price": "142.5",
                    "volume24h": "1000000.0",
                },
                "INVALID": None,
            }
        })
        connected_jupiter._client.get = AsyncMock(return_value=mock_response)

        result = await connected_jupiter.get_price(["So1111..."])
        assert len(result) == 1
        assert isinstance(result[0], PriceTick)
        assert result[0].symbol == "So1111..."
        assert result[0].price == 142.5

    @pytest.mark.asyncio
    async def test_get_price_retries_on_error(self, connected_jupiter):
        connected_jupiter._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(ConnectionError, match="failed after"):
            await connected_jupiter.get_price(["SOL"])


class TestJupiterConnectorGetQuote:
    @pytest.mark.asyncio
    async def test_get_quote_not_connected_raises(self, jupiter_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await jupiter_connector.get_quote("INPUT", "OUTPUT", 1000000)

    @pytest.mark.asyncio
    async def test_get_quote_success(self, connected_jupiter):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "inputMint": "INPUT",
            "outputMint": "OUTPUT",
            "outAmount": "950000",
        })
        connected_jupiter._client.get = AsyncMock(return_value=mock_response)

        result = await connected_jupiter.get_quote("INPUT", "OUTPUT", 1000000)
        assert result["outAmount"] == "950000"

    @pytest.mark.asyncio
    async def test_get_quote_retries_on_http_error(self, connected_jupiter):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        connected_jupiter._client.get = AsyncMock(return_value=mock_response)

        with pytest.raises(ConnectionError, match="failed after"):
            await connected_jupiter.get_quote("INPUT", "OUTPUT", 1000000)


class TestJupiterConnectorRateLimiting:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_requests(self):
        connector = JupiterConnector(api_url="https://mock.jup.ag")
        await connector.connect()
        assert connector._semaphore._value == 10
        await connector.disconnect()
