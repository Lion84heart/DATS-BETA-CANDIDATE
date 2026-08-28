"""Shared pytest fixtures for market connector tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.market.coingecko_connector import CoinGeckoConnector
from src.market.connector_manager import ConnectorManager
from src.market.jupiter_connector import JupiterConnector
from src.market.schemas import OHLCVBar, OrderBookEntry, OrderBookSnapshot, PriceTick, TradeEvent
from src.market.solana_rpc_connector import SolanaRpcConnector


# ---------------------------------------------------------------------------
# Schema fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def price_tick() -> PriceTick:
    return PriceTick(
        symbol="SOL/USDC",
        price=142.5,
        volume=1_000_000.0,
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        source="jupiter",
    )


@pytest.fixture
def order_book_entry() -> OrderBookEntry:
    return OrderBookEntry(price=142.5, size=10.0, side="bid")


@pytest.fixture
def order_book_snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="SOL/USDC",
        bids=[
            OrderBookEntry(price=142.5, size=10.0, side="bid"),
            OrderBookEntry(price=142.4, size=5.0, side="bid"),
        ],
        asks=[
            OrderBookEntry(price=142.6, size=8.0, side="ask"),
            OrderBookEntry(price=142.7, size=3.0, side="ask"),
        ],
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def trade_event() -> TradeEvent:
    return TradeEvent(
        symbol="SOL/USDC",
        price=142.5,
        size=1.5,
        side="buy",
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        signature="abc123",
    )


@pytest.fixture
def ohlcv_bar() -> OHLCVBar:
    return OHLCVBar(
        symbol="SOL/USDC",
        open=140.0,
        high=145.0,
        low=139.0,
        close=142.5,
        volume=500_000.0,
        timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        interval="1m",
    )


# ---------------------------------------------------------------------------
# Connector fixtures (mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_httpx_client():
    """Return a mock httpx.AsyncClient."""
    client = MagicMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def jupiter_connector() -> JupiterConnector:
    return JupiterConnector(api_url="https://mock.jup.ag")


@pytest.fixture
def coingecko_connector() -> CoinGeckoConnector:
    return CoinGeckoConnector(api_url="https://mock.coingecko.com/api/v3")


@pytest.fixture
def coingecko_connector_pro() -> CoinGeckoConnector:
    return CoinGeckoConnector(
        api_url="https://mock.pro.coingecko.com/api/v3",
        api_key="test_pro_key",
    )


@pytest.fixture
def solana_connector() -> SolanaRpcConnector:
    return SolanaRpcConnector(rpc_url="https://mock.solana.rpc")


@pytest.fixture
def connector_manager() -> ConnectorManager:
    return ConnectorManager()


@pytest.fixture
def connected_jupiter(jupiter_connector) -> JupiterConnector:
    """Return a JupiterConnector with a mock client."""
    jupiter_connector._client = MagicMock()
    jupiter_connector._connected = True
    return jupiter_connector


@pytest.fixture
def connected_coingecko(coingecko_connector) -> CoinGeckoConnector:
    """Return a CoinGeckoConnector with a mock client."""
    coingecko_connector._client = MagicMock()
    coingecko_connector._connected = True
    return coingecko_connector


@pytest.fixture
def connected_solana(solana_connector) -> SolanaRpcConnector:
    """Return a SolanaRpcConnector with a mock client."""
    solana_connector._client = MagicMock()
    solana_connector._connected = True
    return solana_connector
