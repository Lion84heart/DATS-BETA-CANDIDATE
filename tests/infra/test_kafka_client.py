"""Tests for ``src.infra.kafka_client`` — Async Kafka Producer & Consumer.

All external I/O is mocked so these tests run without a real Kafka
broker.  Coverage targets:
* Producer lifecycle (start / stop / flush)
* Producer send with JSON serialisation
* Producer retry on start failure
* Consumer lifecycle (start / stop)
* Consumer message yield loop
* Health checks for both producer and consumer
* Topic constants
* KafkaMessage dataclass
* Context-manager entry/exit for both classes
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiokafka.errors import KafkaConnectionError

from src.infra.config import KafkaConfig
from src.infra.kafka_client import (
    _MAX_RETRIES,
    ALL_TOPICS,
    MARKET_DATA,
    PORTFOLIO_UPDATES,
    RISK_ALERTS,
    TRADING_SIGNALS,
    KafkaConsumer,
    KafkaMessage,
    KafkaProducer,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def kafka_config() -> KafkaConfig:
    return KafkaConfig(
        bootstrap_servers="kafka-test:9092",
        client_id="dats-test",
        group_id="test-group",
        retries=3,
        retry_backoff_ms=500,
    )


@pytest.fixture
def producer(kafka_config: KafkaConfig) -> KafkaProducer:
    return KafkaProducer(kafka_config)


@pytest.fixture
def consumer(kafka_config: KafkaConfig) -> KafkaConsumer:
    return KafkaConsumer(kafka_config, topics=[TRADING_SIGNALS, MARKET_DATA])


@pytest.fixture
def mock_aio_producer() -> MagicMock:
    """A mock AIOKafkaProducer with async methods."""
    p = MagicMock()
    p.start = AsyncMock()
    p.stop = AsyncMock()
    p.flush = AsyncMock()
    p.send = AsyncMock()
    p.partitions_for = AsyncMock(return_value={0, 1, 2})
    return p


@pytest.fixture
def mock_aio_consumer() -> MagicMock:
    """A mock AIOKafkaConsumer with async methods."""
    c = MagicMock()
    c.start = AsyncMock()
    c.stop = AsyncMock()
    c.commit = AsyncMock()
    c.subscription = MagicMock(return_value={TRADING_SIGNALS, MARKET_DATA})
    return c


# ===========================================================================
# Topic constants
# ===========================================================================


@pytest.mark.unit
class TestTopicConstants:
    """Ensure topic constants are correctly defined."""

    def test_trading_signals(self) -> None:
        assert TRADING_SIGNALS == "dats.trading.signals"

    def test_portfolio_updates(self) -> None:
        assert PORTFOLIO_UPDATES == "dats.portfolio.updates"

    def test_risk_alerts(self) -> None:
        assert RISK_ALERTS == "dats.risk.alerts"

    def test_market_data(self) -> None:
        assert MARKET_DATA == "dats.market.data"

    def test_all_topics(self) -> None:
        assert len(ALL_TOPICS) == 4
        assert TRADING_SIGNALS in ALL_TOPICS
        assert PORTFOLIO_UPDATES in ALL_TOPICS
        assert RISK_ALERTS in ALL_TOPICS
        assert MARKET_DATA in ALL_TOPICS


# ===========================================================================
# KafkaMessage dataclass
# ===========================================================================


@pytest.mark.unit
class TestKafkaMessage:
    """Tests for the ``KafkaMessage`` dataclass."""

    def test_defaults(self) -> None:
        msg = KafkaMessage(topic=TRADING_SIGNALS, value={"signal": "buy"})
        assert msg.topic == TRADING_SIGNALS
        assert msg.value == {"signal": "buy"}
        assert msg.key is None
        assert msg.partition is None
        assert msg.offset is None
        assert msg.timestamp is None
        assert msg.headers == []

    def test_full(self) -> None:
        msg = KafkaMessage(
            topic=TRADING_SIGNALS,
            value={"signal": "buy"},
            key="AAPL",
            partition=2,
            offset=150,
            timestamp=1700000000000,
            headers=[("version", b"1.0")],
        )
        assert msg.key == "AAPL"
        assert msg.partition == 2
        assert msg.offset == 150
        assert msg.timestamp == 1700000000000
        assert msg.headers == [("version", b"1.0")]


# ===========================================================================
# KafkaProducer
# ===========================================================================


@pytest.mark.unit
class TestProducerStart:
    """Tests for ``KafkaProducer.start``."""

    @pytest.mark.asyncio
    async def test_success(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        with patch("src.infra.kafka_client.AIOKafkaProducer", return_value=mock_aio_producer):
            result = await producer.start()

        assert result is mock_aio_producer
        assert producer.producer is mock_aio_producer
        mock_aio_producer.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_config_passed(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        with patch("src.infra.kafka_client.AIOKafkaProducer") as mock_cls:
            mock_cls.return_value = mock_aio_producer
            await producer.start()

        _, kwargs = mock_cls.call_args
        assert kwargs["bootstrap_servers"] == "kafka-test:9092"
        assert "dats-test-producer" in kwargs["client_id"]
        assert kwargs["acks"] == "all"
        assert kwargs["retries"] == 3
        assert kwargs["retry_backoff_ms"] == 500

    @pytest.mark.asyncio
    async def test_retry_then_success(self, producer: KafkaProducer) -> None:
        mock_p = MagicMock()
        mock_p.start = AsyncMock()
        mock_p.stop = AsyncMock()

        with patch("src.infra.kafka_client.AIOKafkaProducer") as mock_cls:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_cls.side_effect = [
                    MagicMock(start=AsyncMock(side_effect=KafkaConnectionError("fail 1"))),
                    MagicMock(start=AsyncMock(side_effect=KafkaConnectionError("fail 2"))),
                    mock_p,
                ]

                result = await producer.start()
                assert result is mock_p
                assert mock_cls.call_count == 3
                assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, producer: KafkaProducer) -> None:
        with patch("src.infra.kafka_client.AIOKafkaProducer") as mock_cls:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_cls.return_value = MagicMock(
                    start=AsyncMock(side_effect=KafkaConnectionError("always fails"))
                )

                with pytest.raises(ConnectionError, match="Failed to start Kafka producer"):
                    await producer.start()

                assert mock_cls.call_count == _MAX_RETRIES


@pytest.mark.unit
class TestProducerStop:
    """Tests for ``KafkaProducer.stop``."""

    @pytest.mark.asyncio
    async def test_stop_flushes_and_stops(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        producer.producer = mock_aio_producer
        await producer.stop()

        mock_aio_producer.flush.assert_awaited_once()
        mock_aio_producer.stop.assert_awaited_once()
        assert producer.producer is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, producer: KafkaProducer) -> None:
        mock_p = MagicMock()
        mock_p.flush = AsyncMock()
        mock_p.stop = AsyncMock()
        producer.producer = mock_p

        await producer.stop()
        await producer.stop()
        mock_p.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_no_producer(self, producer: KafkaProducer) -> None:
        await producer.stop()  # should not raise


@pytest.mark.unit
class TestProducerSend:
    """Tests for ``KafkaProducer.send``."""

    @pytest.mark.asyncio
    async def test_send_success(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        mock_record = MagicMock()
        mock_record.topic = TRADING_SIGNALS
        mock_record.partition = 2
        mock_record.offset = 150

        # AIOKafkaProducer.send returns a Future;
        # the production code does ``result = await self.producer.send(...)``
        # then ``metadata = await result``.

        future = asyncio.Future()
        future.set_result(mock_record)

        mock_aio_producer.send = AsyncMock(return_value=future)
        producer.producer = mock_aio_producer

        result = await producer.send(TRADING_SIGNALS, {"signal": "buy"}, key="AAPL")

        assert result["topic"] == TRADING_SIGNALS
        assert result["partition"] == 2
        assert result["offset"] == 150

    @pytest.mark.asyncio
    async def test_send_json_serialisation(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:

        mock_record = MagicMock(topic="t", partition=0, offset=1)
        future = asyncio.Future()
        future.set_result(mock_record)

        mock_aio_producer.send = AsyncMock(return_value=future)
        producer.producer = mock_aio_producer

        payload = {"signal": "buy", "ticker": "AAPL", "price": 175.5, "timestamp": "2024-01-01T00:00:00"}
        await producer.send(TRADING_SIGNALS, payload)

        # Verify send was called with JSON-serialized value
        _call_kwargs = mock_aio_producer.send.call_args.kwargs
        assert _call_kwargs["value"] == payload
        assert _call_kwargs["key"] is None

    @pytest.mark.asyncio
    async def test_send_with_key_and_headers(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        future = AsyncMock(return_value=MagicMock(topic="t", partition=0, offset=1))
        mock_aio_producer.send.return_value = future
        producer.producer = mock_aio_producer

        headers = [("version", b"1.0"), ("source", b"test")]
        await producer.send(TRADING_SIGNALS, {"data": 1}, key="KEY-1", headers=headers)

        call_kwargs = mock_aio_producer.send.call_args.kwargs
        assert call_kwargs["key"] == "KEY-1"
        assert call_kwargs["headers"] == headers

    @pytest.mark.asyncio
    async def test_send_not_started(self, producer: KafkaProducer) -> None:
        with pytest.raises(RuntimeError, match="Producer not started"):
            await producer.send(TRADING_SIGNALS, {"data": 1})

    @pytest.mark.asyncio
    async def test_send_failure_returns_error(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        mock_aio_producer.send = AsyncMock(side_effect=KafkaConnectionError("broker down"))
        producer.producer = mock_aio_producer

        result = await producer.send(TRADING_SIGNALS, {"data": 1})

        assert result["topic"] == TRADING_SIGNALS
        assert result["partition"] is None
        assert result["offset"] is None
        assert "broker down" in result["error"]


@pytest.mark.unit
class TestProducerHealthCheck:
    """Tests for ``KafkaProducer.health_check``."""

    @pytest.mark.asyncio
    async def test_healthy(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        producer.producer = mock_aio_producer
        result = await producer.health_check()

        assert result["status"] == "healthy"
        assert result["partitions"] == 3
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_unhealthy_not_started(self, producer: KafkaProducer) -> None:
        result = await producer.health_check()
        assert result["status"] == "unhealthy"
        assert result["error"] == "producer not started"

    @pytest.mark.asyncio
    async def test_unhealthy_partitions_fail(self, producer: KafkaProducer, mock_aio_producer: MagicMock) -> None:
        producer.producer = mock_aio_producer
        mock_aio_producer.partitions_for = AsyncMock(side_effect=KafkaConnectionError("broker down"))

        result = await producer.health_check()
        assert result["status"] == "unhealthy"
        assert "broker down" in result["error"]


# ===========================================================================
# KafkaConsumer
# ===========================================================================


@pytest.mark.unit
class TestConsumerStart:
    """Tests for ``KafkaConsumer.start``."""

    @pytest.mark.asyncio
    async def test_success(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        with patch("src.infra.kafka_client.AIOKafkaConsumer", return_value=mock_aio_consumer):
            result = await consumer.start()

        assert result is mock_aio_consumer
        assert consumer.consumer is mock_aio_consumer
        mock_aio_consumer.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_topics_passed(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        with patch("src.infra.kafka_client.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = mock_aio_consumer
            await consumer.start()

        args, _ = mock_cls.call_args
        assert TRADING_SIGNALS in args
        assert MARKET_DATA in args
        assert PORTFOLIO_UPDATES not in args

    @pytest.mark.asyncio
    async def test_custom_group_id(self, kafka_config: KafkaConfig) -> None:
        consumer = KafkaConsumer(kafka_config, group_id="custom-group")
        mock_c = MagicMock()
        mock_c.start = AsyncMock()

        with patch("src.infra.kafka_client.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = mock_c
            await consumer.start()

        _, kwargs = mock_cls.call_args
        assert kwargs["group_id"] == "custom-group"

    @pytest.mark.asyncio
    async def test_running_flag_set(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        assert consumer._running is False
        with patch("src.infra.kafka_client.AIOKafkaConsumer", return_value=mock_aio_consumer):
            await consumer.start()
        assert consumer._running is True

    @pytest.mark.asyncio
    async def test_retry_then_success(self, consumer: KafkaConsumer) -> None:
        mock_c = MagicMock()
        mock_c.start = AsyncMock()

        with patch("src.infra.kafka_client.AIOKafkaConsumer") as mock_cls:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_cls.side_effect = [
                    MagicMock(start=AsyncMock(side_effect=KafkaConnectionError("fail 1"))),
                    MagicMock(start=AsyncMock(side_effect=KafkaConnectionError("fail 2"))),
                    mock_c,
                ]

                result = await consumer.start()
                assert result is mock_c
                assert mock_cls.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self, consumer: KafkaConsumer) -> None:
        with patch("src.infra.kafka_client.AIOKafkaConsumer") as mock_cls:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_cls.return_value = MagicMock(
                    start=AsyncMock(side_effect=KafkaConnectionError("always fails"))
                )

                with pytest.raises(ConnectionError, match="Failed to start Kafka consumer"):
                    await consumer.start()

                assert mock_cls.call_count == _MAX_RETRIES


@pytest.mark.unit
class TestConsumerStop:
    """Tests for ``KafkaConsumer.stop``."""

    @pytest.mark.asyncio
    async def test_stop(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        consumer.consumer = mock_aio_consumer
        consumer._running = True

        await consumer.stop()

        assert consumer._running is False
        mock_aio_consumer.stop.assert_awaited_once()
        assert consumer.consumer is None

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        consumer.consumer = mock_aio_consumer
        consumer._running = True
        await consumer.stop()
        assert consumer._running is False

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, consumer: KafkaConsumer) -> None:
        mock_c = MagicMock()
        mock_c.stop = AsyncMock()
        consumer.consumer = mock_c

        await consumer.stop()
        await consumer.stop()
        mock_c.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_no_consumer(self, consumer: KafkaConsumer) -> None:
        await consumer.stop()  # should not raise


@pytest.mark.unit
class TestConsumerConsume:
    """Tests for ``KafkaConsumer.consume``."""

    @pytest.mark.asyncio
    async def test_consume_yields_messages(self, consumer: KafkaConsumer) -> None:
        consumer._running = True
        mock_consumer = MagicMock()

        # Build a mock record
        mock_record = MagicMock()
        mock_record.topic = TRADING_SIGNALS
        mock_record.value = {"signal": "buy"}
        mock_record.key = "AAPL"
        mock_record.partition = 1
        mock_record.offset = 42
        mock_record.timestamp = 1700000000000
        mock_record.headers = [("version", b"1.0")]

        # First call returns a batch, second call ends the loop
        call_count = 0

        async def mock_getmany(**_kwargs: Any) -> dict[Any, list[Any]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {MagicMock(): [mock_record]}
            consumer._running = False
            return {}

        mock_consumer.getmany = mock_getmany
        consumer.consumer = mock_consumer

        messages = []
        async for msg in consumer.consume(timeout_ms=100):
            messages.append(msg)
            consumer._running = False  # Stop after first message

        assert len(messages) == 1
        assert isinstance(messages[0], KafkaMessage)
        assert messages[0].topic == TRADING_SIGNALS
        assert messages[0].value == {"signal": "buy"}
        assert messages[0].key == "AAPL"
        assert messages[0].partition == 1
        assert messages[0].offset == 42

    @pytest.mark.asyncio
    async def test_consume_not_started(self, consumer: KafkaConsumer) -> None:
        with pytest.raises(RuntimeError, match="Consumer not started"):
            async for _ in consumer.consume():
                pass

    @pytest.mark.asyncio
    async def test_consume_empty_then_exit(self, consumer: KafkaConsumer) -> None:
        consumer._running = True
        mock_consumer = MagicMock()
        call_count = 0

        async def mock_getmany(**_kwargs: Any) -> dict[Any, list[Any]]:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                consumer._running = False
            return {}

        mock_consumer.getmany = mock_getmany
        consumer.consumer = mock_consumer

        messages = []
        async for msg in consumer.consume(timeout_ms=50):
            messages.append(msg)

        assert len(messages) == 0


@pytest.mark.unit
class TestConsumerCommit:
    """Tests for ``KafkaConsumer.commit``."""

    @pytest.mark.asyncio
    async def test_commit(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        consumer.consumer = mock_aio_consumer
        await consumer.commit()
        mock_aio_consumer.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_not_started(self, consumer: KafkaConsumer) -> None:
        with pytest.raises(RuntimeError, match="Consumer not started"):
            await consumer.commit()


@pytest.mark.unit
class TestConsumerHealthCheck:
    """Tests for ``KafkaConsumer.health_check``."""

    @pytest.mark.asyncio
    async def test_healthy(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        consumer.consumer = mock_aio_consumer
        result = await consumer.health_check()

        assert result["status"] == "healthy"
        assert TRADING_SIGNALS in result["subscribed_topics"]
        assert MARKET_DATA in result["subscribed_topics"]
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_unhealthy_not_started(self, consumer: KafkaConsumer) -> None:
        result = await consumer.health_check()
        assert result["status"] == "unhealthy"
        assert result["error"] == "consumer not started"

    @pytest.mark.asyncio
    async def test_unhealthy_subscription_fails(self, consumer: KafkaConsumer, mock_aio_consumer: MagicMock) -> None:
        consumer.consumer = mock_aio_consumer
        mock_aio_consumer.subscription = MagicMock(side_effect=RuntimeError("Kafka error"))

        result = await consumer.health_check()
        assert result["status"] == "unhealthy"
        assert "Kafka error" in result["error"]


# ===========================================================================
# Serialisation
# ===========================================================================


@pytest.mark.unit
class TestSerialisation:
    """Tests for JSON serialisation / deserialisation."""

    def test_default_serializer(self) -> None:
        from src.infra.kafka_client import _DEFAULT_SERIALIZER
        data = {"signal": "buy", "price": 175.5}
        result = _DEFAULT_SERIALIZER(data)
        assert isinstance(result, bytes)
        assert b"signal" in result
        assert b"buy" in result

    def test_default_deserializer(self) -> None:
        from src.infra.kafka_client import _DEFAULT_DESERIALIZER
        raw = b'{"signal": "buy", "price": 175.5}'
        result = _DEFAULT_DESERIALIZER(raw)
        assert result == {"signal": "buy", "price": 175.5}

    def test_custom_serializer(self, kafka_config: KafkaConfig) -> None:
        custom = lambda v: str(v).upper().encode()  # noqa: E731
        producer = KafkaProducer(kafka_config, serializer=custom)
        assert producer._serializer is custom


# ===========================================================================
# Context managers
# ===========================================================================


@pytest.mark.unit
class TestProducerContextManager:
    """Tests for ``KafkaProducer`` as an async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_starts(self, producer: KafkaProducer) -> None:
        with patch.object(producer, "start", new_callable=AsyncMock) as mock_start:
            async with producer as p:
                assert p is producer
            mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_stops(self, producer: KafkaProducer) -> None:
        with patch.object(producer, "start", new_callable=AsyncMock):
            with patch.object(producer, "stop", new_callable=AsyncMock) as mock_stop:
                async with producer:
                    pass
                mock_stop.assert_awaited_once()


@pytest.mark.unit
class TestConsumerContextManager:
    """Tests for ``KafkaConsumer`` as an async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_starts(self, consumer: KafkaConsumer) -> None:
        with patch.object(consumer, "start", new_callable=AsyncMock) as mock_start:
            async with consumer as c:
                assert c is consumer
            mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_aexit_stops(self, consumer: KafkaConsumer) -> None:
        with patch.object(consumer, "start", new_callable=AsyncMock):
            with patch.object(consumer, "stop", new_callable=AsyncMock) as mock_stop:
                async with consumer:
                    pass
                mock_stop.assert_awaited_once()
