"""DATS — Feature Store (Online + Offline).

Provides dual-storage for ML features:
* **Online store** — Redis (sub-millisecond reads, TTL expiry).
* **Offline store** — TimescaleDB (historical time-series, SQL analytics).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from data.models import FeatureRecord
from infra.database import DatabaseManager
from infra.redis_client import RedisManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TTL_SECONDS: int = 300
_REDIS_KEY_PREFIX: str = "feature"


class FeatureStore:
    """Dual-storage feature store: Redis (online) + TimescaleDB (offline).

    Usage::

        store = FeatureStore(db_manager, redis_manager)

        # Online — fast, ephemeral
        await store.write_online("SOL/USDC", "rsi_14", 65.4, ttl=300)
        val = await store.get_online("SOL/USDC", "rsi_14")  # → 65.4

        # Offline — durable, historical
        await store.write_offline("SOL/USDC", {"rsi_14": 65.4, "ema_9": 142.3})
        rows = await store.get_offline("SOL/USDC", "rsi_14", start, end)
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        redis_manager: RedisManager,
        key_prefix: str = _REDIS_KEY_PREFIX,
    ) -> None:
        self.db: DatabaseManager = db_manager
        self.redis: RedisManager = redis_manager
        self._key_prefix: str = key_prefix

    # -- Key helpers ---------------------------------------------------------

    def _online_key(self, symbol: str, feature: str) -> str:
        return f"{self._key_prefix}:{symbol}:{feature}"

    # -- Online store (Redis) ------------------------------------------------

    async def get_online(self, symbol: str, feature: str) -> float | None:
        """Fetch a single feature value from the online store.

        Args:
            symbol: Trading symbol.
            feature: Feature name.

        Returns:
            The feature value as a float, or ``None`` if missing.
        """
        key = self._online_key(symbol, feature)
        try:
            raw = await self.redis.get(key)
            if raw is None:
                return None
            if isinstance(raw, (int, float)):
                return float(raw)
            if isinstance(raw, dict):
                return float(raw.get("value"))
            if isinstance(raw, str):
                return float(raw)
            return None
        except (ValueError, TypeError) as exc:
            logger.warning("Cannot parse online feature %s: %s", key, exc)
            return None

    async def write_online(
        self,
        symbol: str,
        feature: str,
        value: float,
        ttl: int = _DEFAULT_TTL_SECONDS,
    ) -> bool:
        """Write a single feature value to the online store.

        Args:
            symbol: Trading symbol.
            feature: Feature name.
            value: Numeric feature value.
            ttl: Time-to-live in seconds (default 300).

        Returns:
            ``True`` if the write succeeded.
        """
        key = self._online_key(symbol, feature)
        payload: dict[str, Any] = {
            "value": value,
            "symbol": symbol,
            "feature": feature,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        result = await self.redis.set(key, payload, ttl=ttl)
        if result:
            logger.debug("Online feature written: %s = %s", key, value)
        return result

    async def batch_write_online(
        self,
        symbol: str,
        features: dict[str, float],
        ttl: int = _DEFAULT_TTL_SECONDS,
    ) -> dict[str, bool]:
        """Write multiple feature values for a symbol to the online store.

        Args:
            symbol: Trading symbol.
            features: Mapping of feature name → value.
            ttl: Time-to-live in seconds.

        Returns:
            Mapping of feature name → success bool.
        """
        results: dict[str, bool] = {}
        for feature, value in features.items():
            results[feature] = await self.write_online(symbol, feature, value, ttl=ttl)
        return results

    # -- Offline store (TimescaleDB) -----------------------------------------

    async def get_offline(
        self,
        symbol: str,
        feature: str,
        start: datetime,
        end: datetime,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        """Query historical feature values from the offline store.

        Args:
            symbol: Trading symbol.
            feature: Feature name.
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).
            limit: Maximum rows to return.

        Returns:
            List of dicts with ``timestamp``, ``feature_name``, ``feature_value``.
        """
        from sqlalchemy import select

        stmt = (
            select(FeatureRecord)
            .where(FeatureRecord.symbol == symbol)
            .where(FeatureRecord.feature_name == feature)
            .where(FeatureRecord.timestamp >= start)
            .where(FeatureRecord.timestamp <= end)
            .order_by(FeatureRecord.timestamp.desc())
            .limit(limit)
        )

        rows: list[dict[str, Any]] = []
        async with self.db.get_session() as session:
            result = await session.execute(stmt)
            for record in result.scalars().all():
                rows.append(
                    {
                        "timestamp": record.timestamp,
                        "symbol": record.symbol,
                        "feature_name": record.feature_name,
                        "feature_value": record.feature_value,
                    }
                )
        return rows

    async def write_offline(
        self,
        symbol: str,
        features: dict[str, float],
        timestamp: datetime | None = None,
    ) -> None:
        """Write feature values to the offline store.

        Args:
            symbol: Trading symbol.
            features: Mapping of feature name → value.
            timestamp: Optional timestamp (defaults to now).
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        async with self.db.get_session() as session:
            for feature_name, value in features.items():
                record = FeatureRecord(
                    symbol=symbol,
                    timestamp=timestamp,
                    feature_name=feature_name,
                    feature_value={"value": value},
                )
                session.add(record)

        logger.debug(
            "Offline features written for %s: %d feature(s)",
            symbol,
            len(features),
        )

    async def batch_write_offline(
        self,
        symbol: str,
        features_dict: dict[str, dict[str, float]],
    ) -> None:
        """Write feature values for multiple timestamps to the offline store.

        Args:
            symbol: Trading symbol.
            features_dict: Mapping of ISO timestamp string → feature dict.
                Example::

                    {
                        "2024-01-01T00:00:00+00:00": {"rsi_14": 65.4},
                        "2024-01-01T00:01:00+00:00": {"rsi_14": 62.1},
                    }
        """
        async with self.db.get_session() as session:
            for ts_str, features in features_dict.items():
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                for feature_name, value in features.items():
                    record = FeatureRecord(
                        symbol=symbol,
                        timestamp=ts,
                        feature_name=feature_name,
                        feature_value={"value": value},
                    )
                    session.add(record)

        logger.debug(
            "Batch offline features written for %s: %d timestamp(s)",
            symbol,
            len(features_dict),
        )
