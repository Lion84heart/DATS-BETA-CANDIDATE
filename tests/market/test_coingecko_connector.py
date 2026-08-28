"""Tests for the CoinGecko API connector (mocked HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.market.coingecko_connector import CoinGeckoConnector
from src.market.schemas import OHLCVBar, PriceTick


class TestCoinGeckoConnectorLifecycle:
    @pytest.mark.asyncio
    async def test_connect_free_tier(self, coingecko_connector):
        assert not coingecko_connector.is_connected
        await coingecko_connector.connect()
        assert coingecko_connector.is_connected
        assert coingecko_connector._client is not None

    @pytest.mark.asyncio
    async def test_connect_pro_tier(self, coingecko_connector_pro):
        await coingecko_connector_pro.connect()
        assert coingecko_connector_pro.is_connected

    @pytest.mark.asyncio
    async def test_disconnect(self, coingecko_connector):
        await coingecko_connector.connect()
        assert coingecko_connector.is_connected
        await coingecko_connector.disconnect()
        assert not coingecko_connector.is_connected

    def test_name_property(self, coingecko_connector):
        assert coingecko_connector.name == "coingecko"

    def test_api_url_defaults(self):
        # Without API key → free tier URL
        conn_free = CoinGeckoConnector(api_url=None, api_key=None)
        assert conn_free.api_url == "https://api.coingecko.com/api/v3"

        # With API key → pro tier URL
        conn_pro = CoinGeckoConnector(api_url=None, api_key="test_key")
        assert conn_pro.api_url == "https://pro-api.coingecko.com/api/v3"


class TestCoinGeckoConnectorHealthCheck:
    @pytest.mark.asyncio
    async def test_health_not_connected(self, coingecko_connector):
        health = await coingecko_connector.health_check()
        assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_success(self, connected_coingecko):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"bitcoin": {"usd": 50000}})
        connected_coingecko._client.get = AsyncMock(return_value=mock_response)

        health = await connected_coingecko.health_check()
        assert health["status"] == "healthy"
        assert health["error"] is None


class TestCoinGeckoConnectorGetPrice:
    @pytest.mark.asyncio
    async def test_get_price_not_connected_raises(self, coingecko_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await coingecko_connector.get_price(["solana"])

    @pytest.mark.asyncio
    async def test_get_price_empty_list(self, connected_coingecko):
        result = await connected_coingecko.get_price([])
        assert result == []

    @pytest.mark.asyncio
    async def test_get_price_success(self, connected_coingecko):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "solana": {"usd": 142.5, "usd_24h_vol": 1_000_000},
            "bitcoin": {"usd": 50000},
        })
        connected_coingecko._client.get = AsyncMock(return_value=mock_response)

        result = await connected_coingecko.get_price(["solana", "bitcoin"])
        assert len(result) == 2
        assert isinstance(result[0], PriceTick)
        assert result[0].symbol == "solana"
        assert result[0].price == 142.5

    @pytest.mark.asyncio
    async def test_get_price_retries_on_error(self, connected_coingecko):
        connected_coingecko._client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(ConnectionError, match="failed after"):
            await connected_coingecko.get_price(["solana"])


class TestCoinGeckoConnectorGetOHLCV:
    @pytest.mark.asyncio
    async def test_get_ohlcv_not_connected_raises(self, coingecko_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await coingecko_connector.get_ohlcv("solana")

    @pytest.mark.asyncio
    async def test_get_ohlcv_success(self, connected_coingecko):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        # CoinGecko returns [timestamp, open, high, low, close]
        mock_response.json = MagicMock(return_value=[
            [1704067200000, 140.0, 145.0, 139.0, 142.5],
            [1704153600000, 142.5, 146.0, 141.0, 144.0],
        ])
        connected_coingecko._client.get = AsyncMock(return_value=mock_response)

        result = await connected_coingecko.get_ohlcv("solana", days=2)
        assert len(result) == 2
        assert isinstance(result[0], OHLCVBar)
        assert result[0].symbol == "solana"
        assert result[0].open == 140.0
        assert result[0].high == 145.0
        assert result[0].low == 139.0
        assert result[0].close == 142.5

    @pytest.mark.asyncio
    async def test_get_ohlcv_empty_response(self, connected_coingecko):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=[])
        connected_coingecko._client.get = AsyncMock(return_value=mock_response)

        result = await connected_coingecko.get_ohlcv("solana")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_ohlcv_malformed_row_skipped(self, connected_coingecko):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value=[
            [1704067200000, 140.0, 145.0, 139.0, 142.5],
            "invalid_row",
            [1704153600000, 142.5, 146.0, 141.0, 144.0],
        ])
        connected_coingecko._client.get = AsyncMock(return_value=mock_response)

        result = await connected_coingecko.get_ohlcv("solana")
        assert len(result) == 2
