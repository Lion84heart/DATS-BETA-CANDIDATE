"""DATS — Async SQLAlchemy Database Manager.

Provides a singleton ``DatabaseManager`` that wraps an async SQLAlchemy 2.0
engine and session factory with connection-pooling, retry logic, and health
checks.

Example::

    from infra.config import get_config
    from infra.database import DatabaseManager

    cfg = get_config()
    db = DatabaseManager(cfg.database)
    await db.create_engine()

    async with db.get_session() as session:
        result = await session.execute(select(MyModel))
        rows = result.scalars().all()

    await db.close()
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from infra.config import DatabaseConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
_HEALTH_CHECK_SQL: str = "SELECT 1"


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------


class DatabaseManager:
    """Manages the lifecycle of an async SQLAlchemy engine and sessions.

    Attributes:
        config: ``DatabaseConfig`` instance (DSN, pool settings, etc.).
        engine: The underlying ``AsyncEngine`` (``None`` until
            ``create_engine()`` is called).
        session_factory: ``async_sessionmaker`` bound to *engine*.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self.config: DatabaseConfig = config
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self._scoped_session: async_scoped_session[AsyncSession] | None = None

    # -- Engine lifecycle ----------------------------------------------------

    async def create_engine(self) -> AsyncEngine:
        """Create the async engine with pooling and retry logic.

        On failure, retries up to ``_MAX_RETRIES`` with exponential backoff.

        Returns:
            The created ``AsyncEngine``.

        Raises:
            ConnectionError: If all retry attempts are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self.engine = create_async_engine(
                    self.config.asyncpg_url,
                    pool_size=self.config.pool_size,
                    max_overflow=self.config.max_overflow,
                    pool_recycle=self.config.pool_recycle,
                    pool_timeout=self.config.pool_timeout,
                    pool_pre_ping=True,
                    echo=self.config.echo,
                    future=True,
                )
                logger.info(
                    "Database engine created (pool_size=%d, max_overflow=%d)",
                    self.config.pool_size,
                    self.config.max_overflow,
                )
                return self.engine
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "DB engine creation attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "DB engine creation attempt %d/%d failed: %s — giving up",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )

        raise ConnectionError(
            f"Failed to create DB engine after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def close(self) -> None:
        """Gracefully dispose of the engine and any scoped sessions.

        Safe to call multiple times (idempotent).
        """
        if self._scoped_session is not None:
            try:
                await self._scoped_session.remove()
            except Exception as exc:
                logger.warning("Error removing scoped session: %s", exc)
            self._scoped_session = None
            logger.debug("Scoped session removed.")

        if self.engine is not None:
            try:
                await self.engine.dispose()
            except Exception as exc:
                logger.warning("Error disposing engine: %s", exc)
            finally:
                self.engine = None
                self.session_factory = None
                logger.info("Database engine disposed.")

    # -- Session factory -----------------------------------------------------

    async def _ensure_engine(self) -> None:
        """Lazy-create the engine if it does not yet exist."""
        if self.engine is None:
            await self.create_engine()

    @asynccontextmanager
    async def get_session(
        self,
        expire_on_commit: bool = False,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Provide an async transactional session context manager.

        The session is automatically committed on successful exit and rolled
        back on exception.  It is always closed in the ``finally`` block.

        Args:
            expire_on_commit: Passed to ``AsyncSession``.

        Yields:
            An ``AsyncSession`` instance.
        """
        await self._ensure_engine()

        if self.session_factory is None:
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=expire_on_commit,
                autoflush=False,
                autocommit=False,
            )

        session: AsyncSession = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    def get_scoped_session(self) -> async_scoped_session[AsyncSession]:
        """Return (creating if necessary) an ``async_scoped_session``.

        The scope function uses ``asyncio.current_task`` so each asyncio task
        receives its own isolated session.

        Returns:
            An ``async_scoped_session`` instance.

        Raises:
            RuntimeError: If the engine has not been created.
        """
        if self.engine is None:
            raise RuntimeError(
                "Engine not created — call create_engine() first."
            )

        if self._scoped_session is None:
            session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
            self._scoped_session = async_scoped_session(
                session_factory,
                scopefunc=asyncio.current_task,  # type: ignore[arg-type]
            )
        return self._scoped_session

    # -- Schema helpers ------------------------------------------------------

    async def init_models(self, base: Any | None = None) -> None:
        """Create all declared tables (intended for dev / testing only).

        Args:
            base: SQLAlchemy declarative base with ``metadata``.  If *None*
                the function logs a warning and returns.
        """
        await self._ensure_engine()

        if base is None:
            logger.warning(
                "init_models() called without a declarative base — skipping."
            )
            return

        async with self.engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

        logger.info("Database tables created (init_models).")

    async def drop_models(self, base: Any | None = None) -> None:
        """Drop all declared tables (**destructive** — testing only)."""
        await self._ensure_engine()

        if base is None:
            logger.warning(
                "drop_models() called without a declarative base — skipping."
            )
            return

        async with self.engine.begin() as conn:
            await conn.run_sync(base.metadata.drop_all)

        logger.info("Database tables dropped (drop_models).")

    # -- Health check --------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Execute a lightweight ``SELECT 1`` health probe.

        Returns:
            A dictionary with ``status``, ``latency_ms``, and optional
            ``error`` fields.
        """
        import time

        if self.engine is None:
            return {"status": "unhealthy", "error": "engine not created", "latency_ms": None}

        start = time.perf_counter()
        try:
            async with self.engine.connect() as conn:
                result = await conn.execute(text(_HEALTH_CHECK_SQL))
                row = result.scalar()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy" if row == 1 else "degraded",
                "latency_ms": latency_ms,
                "error": None,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("DB health check failed: %s", exc)
            return {"status": "unhealthy", "latency_ms": latency_ms, "error": str(exc)}

    # -- Magic helpers -------------------------------------------------------

    async def __aenter__(self) -> DatabaseManager:
        await self.create_engine()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()
