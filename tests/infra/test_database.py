"""Tests for ``src.infra.database`` — Async SQLAlchemy Database Manager.

All external I/O is mocked so these tests run without a real PostgreSQL
instance.  Coverage targets:
* Engine creation (with retry)
* Session context manager (commit / rollback)
* Scoped sessions
* Health check (healthy & unhealthy paths)
* Async context-manager entry/exit
* Close / dispose idempotency
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.infra.config import DatabaseConfig
from src.infra.database import (
    _BACKOFF_MAX_SECONDS,
    _MAX_RETRIES,
    DatabaseManager,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_config() -> DatabaseConfig:
    return DatabaseConfig(
        host="test-db",
        port=5432,
        user="test",
        password="test",
        name="testdb",
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


@pytest.fixture
def manager(db_config: DatabaseConfig) -> DatabaseManager:
    return DatabaseManager(db_config)


@pytest.fixture
def mock_engine() -> MagicMock:
    """A mock AsyncEngine with async methods."""
    engine = MagicMock(spec=AsyncEngine)
    engine.dispose = AsyncMock()
    engine.begin = MagicMock()
    engine.connect = MagicMock()
    return engine


@pytest.fixture
def mock_session() -> MagicMock:
    """A mock AsyncSession with async methods."""
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.execute = AsyncMock()
    return session


# ===========================================================================
# Engine lifecycle
# ===========================================================================


@pytest.mark.unit
class TestCreateEngine:
    """Tests for ``DatabaseManager.create_engine``."""

    @pytest.mark.asyncio
    async def test_success(self, manager: DatabaseManager) -> None:
        with patch("src.infra.database.create_async_engine") as mock_create:
            mock_engine = MagicMock(spec=AsyncEngine)
            mock_create.return_value = mock_engine

            result = await manager.create_engine()

            assert result is mock_engine
            assert manager.engine is mock_engine
            mock_create.assert_called_once()
            # Verify DSN contains expected parts
            dsn = mock_create.call_args[0][0]
            assert "postgresql+asyncpg://" in dsn
            assert "test-db" in dsn
            assert "testdb" in dsn

    @pytest.mark.asyncio
    async def test_pool_settings_passed(self, manager: DatabaseManager) -> None:
        with patch("src.infra.database.create_async_engine") as mock_create:
            mock_create.return_value = MagicMock(spec=AsyncEngine)
            await manager.create_engine()

            _, kwargs = mock_create.call_args
            assert kwargs["pool_size"] == 5
            assert kwargs["max_overflow"] == 10
            assert kwargs["pool_pre_ping"] is True
            assert kwargs["future"] is True

    @pytest.mark.asyncio
    async def test_retry_then_success(self, manager: DatabaseManager) -> None:
        """Engine creation fails twice then succeeds on 3rd attempt."""
        with patch("src.infra.database.create_async_engine") as mock_create:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_engine = MagicMock(spec=AsyncEngine)
                mock_create.side_effect = [
                    ConnectionError("fail 1"),
                    ConnectionError("fail 2"),
                    mock_engine,
                ]

                result = await manager.create_engine()

                assert result is mock_engine
                assert mock_create.call_count == 3
                assert mock_sleep.call_count == 2
                # Verify exponential backoff
                mock_sleep.assert_any_call(1.0)  # 1 * 2^0
                mock_sleep.assert_any_call(2.0)  # 1 * 2^1

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, manager: DatabaseManager) -> None:
        """All retry attempts fail — should raise ConnectionError."""
        with patch("src.infra.database.create_async_engine") as mock_create:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_create.side_effect = ConnectionError("always fails")

                with pytest.raises(ConnectionError, match="Failed to create DB engine"):
                    await manager.create_engine()

                assert mock_create.call_count == _MAX_RETRIES
                assert mock_sleep.call_count == _MAX_RETRIES - 1

    @pytest.mark.asyncio
    async def test_backoff_capped(self, manager: DatabaseManager) -> None:
        """Exponential backoff should not exceed max."""
        with patch("src.infra.database.create_async_engine") as mock_create:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_create.side_effect = [
                    ConnectionError(f"fail {i}") for i in range(_MAX_RETRIES - 1)
                ] + [MagicMock(spec=AsyncEngine)]

                await manager.create_engine()
                for call in mock_sleep.call_args_list:
                    wait_time = call[0][0]
                    assert wait_time <= _BACKOFF_MAX_SECONDS


@pytest.mark.unit
class TestClose:
    """Tests for ``DatabaseManager.close``."""

    @pytest.mark.asyncio
    async def test_close_disposes_engine(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        await manager.close()
        mock_engine.dispose.assert_awaited_once()
        assert manager.engine is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self, manager: DatabaseManager) -> None:
        """Calling close() twice should not raise."""
        mock_engine = MagicMock(spec=AsyncEngine)
        mock_engine.dispose = AsyncMock()
        manager.engine = mock_engine

        await manager.close()
        await manager.close()  # second close — should be safe
        mock_engine.dispose.assert_awaited_once()
        assert manager.engine is None

    @pytest.mark.asyncio
    async def test_close_no_engine(self, manager: DatabaseManager) -> None:
        """Closing before engine creation should not raise."""
        await manager.close()  # should not raise

    @pytest.mark.asyncio
    async def test_close_removes_scoped_session(
        self, manager: DatabaseManager, mock_engine: MagicMock
    ) -> None:
        manager.engine = mock_engine
        scoped = MagicMock()
        scoped.remove = AsyncMock()
        manager._scoped_session = scoped  # type: ignore[assignment]

        await manager.close()
        scoped.remove.assert_awaited_once()
        assert manager._scoped_session is None


# ===========================================================================
# Session management
# ===========================================================================


@pytest.mark.unit
class TestGetSession:
    """Tests for ``DatabaseManager.get_session`` context manager."""

    @pytest.mark.asyncio
    async def test_session_commit_on_success(
        self, manager: DatabaseManager, mock_engine: MagicMock, mock_session: MagicMock
    ) -> None:
        manager.engine = mock_engine
        mock_factory = MagicMock(return_value=mock_session)
        manager.session_factory = mock_factory  # type: ignore[assignment]

        async with manager.get_session() as session:
            assert session is mock_session

        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_rollback_on_error(
        self, manager: DatabaseManager, mock_engine: MagicMock, mock_session: MagicMock
    ) -> None:
        manager.engine = mock_engine
        mock_factory = MagicMock(return_value=mock_session)
        manager.session_factory = mock_factory  # type: ignore[assignment]

        with pytest.raises(ValueError, match="boom"):
            async with manager.get_session() as session:
                assert session is mock_session
                raise ValueError("boom")

        mock_session.commit.assert_not_awaited()
        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_closed_on_error(
        self, manager: DatabaseManager, mock_engine: MagicMock, mock_session: MagicMock
    ) -> None:
        manager.engine = mock_engine
        mock_factory = MagicMock(return_value=mock_session)
        manager.session_factory = mock_factory  # type: ignore[assignment]

        try:
            async with manager.get_session():
                raise RuntimeError("crash")
        except RuntimeError:
            pass

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lazy_engine_creation(self, manager: DatabaseManager) -> None:
        """get_session should auto-create engine if not present."""
        with patch.object(manager, "create_engine", new_callable=AsyncMock) as mock_create:
            mock_engine = MagicMock(spec=AsyncEngine)
            mock_create.return_value = mock_engine

            mock_session = MagicMock(spec=AsyncSession)
            mock_session.commit = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.close = AsyncMock()

            with patch("src.infra.database.async_sessionmaker") as mock_sessionmaker_cls:
                mock_sessionmaker_cls.return_value = MagicMock(return_value=mock_session)
                async with manager.get_session() as session:
                    assert session is mock_session

            mock_create.assert_awaited_once()


# ===========================================================================
# Scoped session
# ===========================================================================


@pytest.mark.unit
class TestScopedSession:
    """Tests for ``DatabaseManager.get_scoped_session``."""

    def test_raises_when_no_engine(self, manager: DatabaseManager) -> None:
        with pytest.raises(RuntimeError, match="Engine not created"):
            manager.get_scoped_session()

    @pytest.mark.asyncio
    async def test_returns_scoped_session(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        scoped = manager.get_scoped_session()
        assert scoped is not None
        # Calling again returns cached instance
        scoped2 = manager.get_scoped_session()
        assert scoped is scoped2


# ===========================================================================
# Schema helpers
# ===========================================================================


@pytest.mark.unit
class TestInitModels:
    """Tests for ``DatabaseManager.init_models``."""

    @pytest.mark.asyncio
    async def test_with_base(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        mock_metadata = MagicMock()
        mock_metadata.create_all = MagicMock()
        mock_base = MagicMock()
        mock_base.metadata = mock_metadata

        # Mock engine.begin as async context manager
        mock_conn = MagicMock()
        mock_conn.run_sync = AsyncMock()
        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_begin_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_engine.begin.return_value = mock_begin_ctx

        await manager.init_models(mock_base)
        mock_begin_ctx.__aenter__.assert_awaited_once()
        mock_conn.run_sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_without_base(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        # Should not raise and should return early
        await manager.init_models(None)
        mock_engine.begin.assert_not_called()


@pytest.mark.unit
class TestDropModels:
    """Tests for ``DatabaseManager.drop_models``."""

    @pytest.mark.asyncio
    async def test_with_base(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        mock_base = MagicMock()
        mock_conn = MagicMock()
        mock_conn.run_sync = AsyncMock()
        mock_begin_ctx = AsyncMock()
        mock_begin_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_begin_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_engine.begin.return_value = mock_begin_ctx

        await manager.drop_models(mock_base)
        mock_conn.run_sync.assert_awaited_once()


# ===========================================================================
# Health check
# ===========================================================================


@pytest.mark.unit
class TestHealthCheck:
    """Tests for ``DatabaseManager.health_check``."""

    @pytest.mark.asyncio
    async def test_healthy(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_connect_ctx = AsyncMock()
        mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect.return_value = mock_connect_ctx

        result = await manager.health_check()

        assert result["status"] == "healthy"
        assert result["latency_ms"] is not None
        assert result["error"] is None
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_no_engine(self, manager: DatabaseManager) -> None:
        result = await manager.health_check()
        assert result["status"] == "unhealthy"
        assert result["error"] == "engine not created"
        assert result["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_unhealthy_exception(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        manager.engine = mock_engine
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(side_effect=ConnectionError("DB down"))
        mock_connect_ctx = AsyncMock()
        mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect.return_value = mock_connect_ctx

        result = await manager.health_check()

        assert result["status"] == "unhealthy"
        assert result["error"] == "DB down"
        assert result["latency_ms"] is not None

    @pytest.mark.asyncio
    async def test_degraded_wrong_value(self, manager: DatabaseManager, mock_engine: MagicMock) -> None:
        """SELECT 1 returns unexpected value → degraded."""
        manager.engine = mock_engine
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42  # not 1

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value=mock_result)
        mock_connect_ctx = AsyncMock()
        mock_connect_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_connect_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_engine.connect.return_value = mock_connect_ctx

        result = await manager.health_check()
        assert result["status"] == "degraded"


# ===========================================================================
# Async context manager
# ===========================================================================


@pytest.mark.unit
class TestAsyncContextManager:
    """Tests for ``DatabaseManager`` as an async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_creates_engine(self, manager: DatabaseManager) -> None:
        with patch.object(manager, "create_engine", new_callable=AsyncMock) as mock_create:
            async with manager as mgr:
                assert mgr is manager
            mock_create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_closes(self, manager: DatabaseManager) -> None:
        with patch.object(manager, "create_engine", new_callable=AsyncMock):
            with patch.object(manager, "close", new_callable=AsyncMock) as mock_close:
                async with manager:
                    pass
                mock_close.assert_awaited_once()
