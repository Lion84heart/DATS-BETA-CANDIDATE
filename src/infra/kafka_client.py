"""DATS — Async Kafka Producer & Consumer.

Provides ``KafkaProducer`` and ``KafkaConsumer`` classes built on top of
``aiokafka`` with connection retry, JSON serialization, graceful shutdown,
and health-check endpoints.

Topic constants are exposed as module-level strings so downstream code can
import them directly::

    from infra.kafka_client import KafkaProducer, TRADING_SIGNALS

    producer = KafkaProducer(config)
    await producer.send(TRADING_SIGNALS, {"signal": "buy", "ticker": "AAPL"})

"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaError

from infra.config import KafkaConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic constants
# ---------------------------------------------------------------------------

TRADING_SIGNALS: str = "dats.trading.signals"
PORTFOLIO_UPDATES: str = "dats.portfolio.updates"
RISK_ALERTS: str = "dats.risk.alerts"
MARKET_DATA: str = "dats.market.data"

ALL_TOPICS: list[str] = [
    TRADING_SIGNALS,
    PORTFOLIO_UPDATES,
    RISK_ALERTS,
    MARKET_DATA,
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 1.0
_BACKOFF_MAX_SECONDS: float = 8.0
_DEFAULT_SERIALIZER: Callable[[Any], bytes] = lambda v: json.dumps(
    v, default=str
).encode("utf-8")
_DEFAULT_DESERIALIZER: Callable[[bytes], Any] = lambda v: json.loads(
    v.decode("utf-8")
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class KafkaMessage:
    """Normalised message envelope produced or consumed by DATS.

    Attributes:
        topic: Kafka topic name.
        key: Optional message key (used for partitioning).
        value: Deserialised message payload.
        partition: Partition number (set on consumption).
        offset: Message offset (set on consumption).
        timestamp: Milliseconds since epoch (set on consumption).
        headers: Optional list of (key, value) tuples.
    """

    topic: str
    value: Any
    key: str | None = None
    partition: int | None = None
    offset: int | None = None
    timestamp: int | None = None
    headers: list[tuple[str, bytes]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KafkaProducer
# ---------------------------------------------------------------------------


class KafkaProducer:
    """Async Kafka producer with JSON serialisation and retry logic.

    Attributes:
        config: ``KafkaConfig`` instance.
        producer: The underlying ``AIOKafkaProducer`` (``None`` until
            ``start()`` is called).
    """

    def __init__(
        self,
        config: KafkaConfig,
        *,
        serializer: Callable[[Any], bytes] | None = None,
    ) -> None:
        self.config: KafkaConfig = config
        self._serializer: Callable[[Any], bytes] = serializer or _DEFAULT_SERIALIZER
        self.producer: AIOKafkaProducer | None = None

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> AIOKafkaProducer:
        """Start the producer with retry logic.

        Returns:
            The started ``AIOKafkaProducer``.

        Raises:
            ConnectionError: If all retry attempts are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self.producer = AIOKafkaProducer(
                    bootstrap_servers=self.config.bootstrap_servers,
                    client_id=f"{self.config.client_id}-producer",
                    acks=self.config.acks,
                    retries=self.config.retries,
                    retry_backoff_ms=self.config.retry_backoff_ms,
                    request_timeout_ms=self.config.request_timeout_ms,
                    value_serializer=self._serializer,
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                )
                await self.producer.start()
                logger.info(
                    "Kafka producer started (bootstrap=%s)",
                    self.config.bootstrap_servers,
                )
                return self.producer
            except (KafkaConnectionError, KafkaError, OSError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "Kafka producer start attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Kafka producer start attempt %d/%d failed: %s — giving up",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )

        raise ConnectionError(
            f"Failed to start Kafka producer after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def stop(self) -> None:
        """Gracefully flush pending messages and stop the producer.

        Idempotent — safe to call multiple times.
        """
        if self.producer is not None:
            try:
                await self.producer.flush()
                logger.debug("Kafka producer flushed.")
            except Exception as exc:
                logger.warning("Kafka producer flush error: %s", exc)
            finally:
                await self.producer.stop()
                self.producer = None
                logger.info("Kafka producer stopped.")

    # -- Produce --------------------------------------------------------------

    async def send(
        self,
        topic: str,
        value: Any,
        *,
        key: str | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> dict[str, Any]:
        """Send a JSON-serialised message to *topic*.

        Args:
            topic: Target Kafka topic.
            value: Any JSON-serialisable payload.
            key: Optional string key for partitioning.
            headers: Optional list of (key, value) header tuples.

        Returns:
            Metadata dict with ``topic``, ``partition``, and ``offset``
            (all ``None`` if the send failed).

        Raises:
            RuntimeError: If the producer has not been started.
        """
        if self.producer is None:
            raise RuntimeError(
                "Producer not started — call start() first."
            )

        try:
            result = await self.producer.send(
                topic,
                value=value,
                key=key,
                headers=headers or [],
            )
            # result is a RecordMetadata future
            metadata = await result
            logger.debug(
                "Produced to %s partition=%d offset=%d",
                topic,
                metadata.partition,
                metadata.offset,
            )
            return {
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
            }
        except Exception as exc:
            logger.error("Failed to produce message to %s: %s", topic, exc)
            return {"topic": topic, "partition": None, "offset": None, "error": str(exc)}

    # -- Health check --------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check producer health by verifying it is started.

        Returns:
            Dict with ``status`` and ``error`` fields.
        """
        if self.producer is None:
            return {"status": "unhealthy", "error": "producer not started"}
        try:
            # Check partitions for a known topic as a connectivity test
            partitions = await self.producer.partitions_for(TRADING_SIGNALS)
            return {
                "status": "healthy",
                "partitions": len(partitions),
                "error": None,
            }
        except Exception as exc:
            logger.error("Kafka producer health check failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}

    # -- Context manager -----------------------------------------------------

    async def __aenter__(self) -> KafkaProducer:
        await self.start()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.stop()


# ---------------------------------------------------------------------------
# KafkaConsumer
# ---------------------------------------------------------------------------


class KafkaConsumer:
    """Async Kafka consumer with JSON deserialisation and graceful shutdown.

    Attributes:
        config: ``KafkaConfig`` instance.
        consumer: The underlying ``AIOKafkaConsumer`` (``None`` until
            ``start()`` is called).
        topics: List of topic names to subscribe to.
    """

    def __init__(
        self,
        config: KafkaConfig,
        topics: list[str] | None = None,
        *,
        deserializer: Callable[[bytes], Any] | None = None,
        group_id: str | None = None,
    ) -> None:
        self.config: KafkaConfig = config
        self.topics: list[str] = topics or ALL_TOPICS
        self._deserializer: Callable[[bytes], Any] = (
            deserializer or _DEFAULT_DESERIALIZER
        )
        self._group_id: str = group_id or config.group_id
        self.consumer: AIOKafkaConsumer | None = None
        self._running: bool = False

    # -- Lifecycle -----------------------------------------------------------

    async def start(self) -> AIOKafkaConsumer:
        """Start the consumer and subscribe to topics with retry logic.

        Returns:
            The started ``AIOKafkaConsumer``.

        Raises:
            ConnectionError: If all retry attempts are exhausted.
        """
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self.consumer = AIOKafkaConsumer(
                    *self.topics,
                    bootstrap_servers=self.config.bootstrap_servers,
                    client_id=f"{self.config.client_id}-consumer",
                    group_id=self._group_id,
                    auto_offset_reset=self.config.auto_offset_reset,
                    enable_auto_commit=self.config.enable_auto_commit,
                    max_poll_records=self.config.max_poll_records,
                    session_timeout_ms=self.config.session_timeout_ms,
                    request_timeout_ms=self.config.request_timeout_ms,
                    value_deserializer=self._deserializer,
                    key_deserializer=lambda k: k.decode("utf-8") if k else None,
                )
                await self.consumer.start()
                self._running = True
                logger.info(
                    "Kafka consumer started (topics=%s, group=%s)",
                    self.topics,
                    self._group_id,
                )
                return self.consumer
            except (KafkaConnectionError, KafkaError, OSError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = min(
                        _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)),
                        _BACKOFF_MAX_SECONDS,
                    )
                    logger.warning(
                        "Kafka consumer start attempt %d/%d failed: %s — retrying in %.1fs",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Kafka consumer start attempt %d/%d failed: %s — giving up",
                        attempt,
                        _MAX_RETRIES,
                        exc,
                    )

        raise ConnectionError(
            f"Failed to start Kafka consumer after {_MAX_RETRIES} attempts"
        ) from last_exc

    async def stop(self) -> None:
        """Gracefully stop the consumer.

        Idempotent — safe to call multiple times.
        """
        self._running = False
        if self.consumer is not None:
            try:
                await self.consumer.stop()
                logger.info("Kafka consumer stopped.")
            except Exception as exc:
                logger.warning("Kafka consumer stop error: %s", exc)
            finally:
                self.consumer = None

    # -- Consume --------------------------------------------------------------

    async def consume(
        self,
        timeout_ms: int = 1000,
    ) -> AsyncGenerator[KafkaMessage, None]:
        """Asynchronously yield ``KafkaMessage`` records from subscribed topics.

        The generator runs until ``stop()`` is called (sets ``_running`` to
        ``False``), making it suitable for long-running background tasks::

            async for msg in consumer.consume():
                await process(msg)

        Args:
            timeout_ms: Maximum milliseconds to wait for a message batch.

        Yields:
            ``KafkaMessage`` instances.
        """
        if self.consumer is None:
            raise RuntimeError(
                "Consumer not started — call start() first."
            )

        logger.info("Consumer loop started (timeout_ms=%d).", timeout_ms)
        try:
            while self._running:
                try:
                    result = await self.consumer.getmany(
                        timeout_ms=timeout_ms,
                        max_records=self.config.max_poll_records,
                    )
                    if not result:
                        continue

                    for tp, messages in result.items():
                        for record in messages:
                            yield KafkaMessage(
                                topic=record.topic,
                                value=record.value,
                                key=record.key,
                                partition=record.partition,
                                offset=record.offset,
                                timestamp=record.timestamp,
                                headers=list(record.headers) if record.headers else [],
                            )
                except Exception as exc:
                    if self._running:
                        logger.error("Error in consumer loop: %s", exc)
                        await asyncio.sleep(1)
        finally:
            logger.info("Consumer loop exited.")

    async def commit(self) -> None:
        """Manually commit offsets (when auto-commit is disabled)."""
        if self.consumer is None:
            raise RuntimeError("Consumer not started.")
        await self.consumer.commit()
        logger.debug("Offsets committed.")

    # -- Health check --------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Check consumer health by verifying subscription status.

        Returns:
            Dict with ``status``, ``subscribed_topics``, and ``error``.
        """
        if self.consumer is None:
            return {"status": "unhealthy", "error": "consumer not started"}
        try:
            subscriptions = self.consumer.subscription()
            return {
                "status": "healthy",
                "subscribed_topics": list(subscriptions) if subscriptions else [],
                "error": None,
            }
        except Exception as exc:
            logger.error("Kafka consumer health check failed: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}

    # -- Context manager -----------------------------------------------------

    async def __aenter__(self) -> KafkaConsumer:
        await self.start()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.stop()
