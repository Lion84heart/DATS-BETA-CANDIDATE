"""Tests for the Solana RPC connector (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.market.solana_rpc_connector import SolanaRpcConnector


class TestSolanaRpcConnectorLifecycle:
    @pytest.mark.asyncio
    async def test_connect(self, solana_connector):
        assert not solana_connector.is_connected
        await solana_connector.connect()
        assert solana_connector.is_connected
        assert solana_connector._client is not None

    @pytest.mark.asyncio
    async def test_disconnect(self, solana_connector):
        await solana_connector.connect()
        assert solana_connector.is_connected
        await solana_connector.disconnect()
        assert not solana_connector.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, solana_connector):
        await solana_connector.disconnect()
        assert not solana_connector.is_connected

    def test_name_property(self, solana_connector):
        assert solana_connector.name == "solana_rpc"


class TestSolanaRpcConnectorHealthCheck:
    @pytest.mark.asyncio
    async def test_health_not_connected(self, solana_connector):
        health = await solana_connector.health_check()
        assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_success(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": "ok",
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        health = await connected_solana.health_check()
        assert health["status"] == "healthy"
        assert health["error"] is None

    @pytest.mark.asyncio
    async def test_health_degraded(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": "behind",
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        health = await connected_solana.health_check()
        assert health["status"] == "degraded"


class TestSolanaRpcGetAccountInfo:
    @pytest.mark.asyncio
    async def test_get_account_info_not_connected_raises(self, solana_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await solana_connector.get_account_info("SomePubkey")

    @pytest.mark.asyncio
    async def test_get_account_info_success(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": {"lamports": 1000000, "owner": "SystemProgram"},
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        result = await connected_solana.get_account_info("SomePubkey")
        assert result["lamports"] == 1000000


class TestSolanaRpcGetTokenAccounts:
    @pytest.mark.asyncio
    async def test_get_token_accounts_not_connected_raises(self, solana_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await solana_connector.get_token_accounts("OwnerPubkey")

    @pytest.mark.asyncio
    async def test_get_token_accounts_success(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": {
                "value": [
                    {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 100}}}}}},
                ]
            },
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        result = await connected_solana.get_token_accounts("OwnerPubkey")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_token_accounts_empty_result(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": {},
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        result = await connected_solana.get_token_accounts("OwnerPubkey")
        assert result == []


class TestSolanaRpcGetSignatures:
    @pytest.mark.asyncio
    async def test_get_signatures_not_connected_raises(self, solana_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await solana_connector.get_signatures_for_address("Address")

    @pytest.mark.asyncio
    async def test_get_signatures_success(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": [
                {"signature": "sig1", "slot": 123},
                {"signature": "sig2", "slot": 124},
            ],
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        result = await connected_solana.get_signatures_for_address("Address", limit=2)
        assert len(result) == 2
        assert result[0]["signature"] == "sig1"


class TestSolanaRpcGetTransaction:
    @pytest.mark.asyncio
    async def test_get_transaction_not_connected_raises(self, solana_connector):
        with pytest.raises(RuntimeError, match="not connected"):
            await solana_connector.get_transaction("sig123")

    @pytest.mark.asyncio
    async def test_get_transaction_success(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": {"slot": 123, "meta": {"fee": 5000}},
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        result = await connected_solana.get_transaction("sig123")
        assert result["slot"] == 123


class TestSolanaRpcErrorHandling:
    @pytest.mark.asyncio
    async def test_rpc_error_raises(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": "Server error"},
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(RuntimeError, match="Solana RPC error"):
            await connected_solana.get_account_info("Pubkey")

    @pytest.mark.asyncio
    async def test_connection_error_retries(self, connected_solana):
        connected_solana._client.post = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        with pytest.raises(ConnectionError, match="failed after"):
            await connected_solana.get_account_info("Pubkey")

    @pytest.mark.asyncio
    async def test_request_id_increments(self, connected_solana):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={
            "jsonrpc": "2.0",
            "result": {},
            "id": 1,
        })
        connected_solana._client.post = AsyncMock(return_value=mock_response)

        await connected_solana.get_account_info("Pubkey1")
        assert connected_solana._request_id == 1

        await connected_solana.get_account_info("Pubkey2")
        assert connected_solana._request_id == 2
