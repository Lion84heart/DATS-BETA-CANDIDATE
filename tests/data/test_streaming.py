"""Tests for the DataStreamPipeline (Kafka integration)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.data.streaming import DataStreamPipeline
from src.infra.kafka_client import MARKET_DATA, KafkaMessage
from src.market.schemas import OHLCVBar, PriceTick


class TestDataStreamPipelineInit:
    def test_init(self, mock_kafka_producer, mock_kafka_consumer):
        pipeline = DataStreamPipeline(mock_kafka_producer, mock_kafka_consumer)
        assert pipeline.producer is mock_kafka_producer
        assert pipeline.consumer is mock_kafka_consumer


class TestDataStreamPipelinePublishTick:
    @pytest.mark.asyncio
    async def test_publish_tick(self, data_stream_pipeline, mock_kafka_producer):
        tick = PriceTick(
            symbol="SOL/USDC",
            price=142.5,
            volume=1000000.0,
            timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            source="jupiter",
        )
        result = await data_stream_pipeline.publish_tick(tick)
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["key"] == "SOL/USDC"
        assert call_args.kwargs["value"]["type"] == "tick"
        assert call_args.kwargs["value"]["price"] == 142.5

    @pytest.mark.asyncio
    async def test_publish_tick_send_failure(self, data_stream_pipeline, mock_kafka_producer):
        mock_kafka_producer.send = AsyncMock(return_value={
            "topic": "test", "partition": None, "offset": None, "error": "timeout"
        })
        tick = PriceTick(
            symbol="SOL/USDC",
            price=142.5,
            volume=1000000.0,
            timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        )
        result = await data_stream_pipeline.publish_tick(tick)
        assert "error" in result


class TestDataStreamPipelinePublishBar:
    @pytest.mark.asyncio
    async def test_publish_bar(self, data_stream_pipeline, mock_kafka_producer):
        bar = OHLCVBar(
            symbol="SOL/USDC",
            open=140.0,
            high=145.0,
            low=139.0,
            close=142.5,
            volume=500000.0,
            timestamp=datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            interval="1m",
        )
        result = await data_stream_pipeline.publish_bar(bar)
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["value"]["type"] == "bar"
        assert call_args.kwargs["value"]["open"] == 140.0
        assert call_args.kwargs["value"]["high"] == 145.0


class TestDataStreamPipelinePublishFeatures:
    @pytest.mark.asyncio
    async def test_publish_features(self, data_stream_pipeline, mock_kafka_producer):
        features = {"rsi_14": 65.4, "ema_9": 142.3, "null_feature": None}
        result = await data_stream_pipeline.publish_features("SOL/USDC", features)
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        payload = call_args.kwargs["value"]
        assert payload["type"] == "features"
        assert payload["symbol"] == "SOL/USDC"
        assert payload["features"]["rsi_14"] == 65.4
        assert payload["features"]["null_feature"] == "nan"

    @pytest.mark.asyncio
    async def test_publish_features_empty(self, data_stream_pipeline, mock_kafka_producer):
        result = await data_stream_pipeline.publish_features("SOL/USDC", {})
        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args.kwargs["value"]["features"] == {}


class TestDataStreamPipelineConsumeTicks:
    @pytest.mark.asyncio
    async def test_consume_ticks(self, data_stream_pipeline, mock_kafka_consumer):
        tick_data = {
            "type": "tick",
            "symbol": "SOL/USDC",
            "price": 142.5,
            "volume": 1000000.0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "jupiter",
        }
        msg = KafkaMessage(topic="dats.market.data", value=tick_data)

        async def mock_consume(*args, **kwargs):
            yield msg
            # Give time for callback to run, then stop
            await asyncio.sleep(0.01)

        mock_kafka_consumer.consume = mock_consume

        received = []
        async def callback(tick):
            received.append(tick)
            data_stream_pipeline.stop()

        await data_stream_pipeline.consume_ticks(callback)

        assert len(received) == 1
        assert isinstance(received[0], PriceTick)
        assert received[0].symbol == "SOL/USDC"
        assert received[0].price == 142.5

    @pytest.mark.asyncio
    async def test_consume_ticks_wrong_type_ignored(self, data_stream_pipeline, mock_kafka_consumer):
        msg = KafkaMessage(topic="dats.market.data", value={"type": "bar"})

        async def mock_consume(*args, **kwargs):
            yield msg
            await asyncio.sleep(0.01)

        mock_kafka_consumer.consume = mock_consume

        received = []
        async def callback(tick):
            received.append(tick)

        # Stop after processing the message (which will be skipped due to wrong type)
        asyncio.get_event_loop().call_later(0.05, data_stream_pipeline.stop)
        await data_stream_pipeline.consume_ticks(callback)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_consume_ticks_error_handling(self, data_stream_pipeline, mock_kafka_consumer):
        tick_data = {
            "type": "tick",
            "symbol": "SOL/USDC",
            "price": 142.5,
            "volume": 1000000.0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "jupiter",
        }
        msg = KafkaMessage(topic="dats.market.data", value=tick_data)

        async def mock_consume(*args, **kwargs):
            yield msg
            await asyncio.sleep(0.01)

        mock_kafka_consumer.consume = mock_consume

        async def bad_callback(tick):
            data_stream_pipeline.stop()
            raise ValueError("boom")

        # Should not raise — error is logged and swallowed
        await data_stream_pipeline.consume_ticks(bad_callback)


class TestDataStreamPipelineConsumeBars:
    @pytest.mark.asyncio
    async def test_consume_bars(self, data_stream_pipeline, mock_kafka_consumer):
        bar_data = {
            "type": "bar",
            "symbol": "SOL/USDC",
            "open": 140.0,
            "high": 145.0,
            "low": 139.0,
            "close": 142.5,
            "volume": 500000.0,
            "timestamp": "2024-01-01T00:00:00+00:00",
            "interval": "1m",
        }
        msg = KafkaMessage(topic="dats.market.data", value=bar_data)

        async def mock_consume(*args, **kwargs):
            yield msg
            await asyncio.sleep(0.01)

        mock_kafka_consumer.consume = mock_consume

        received = []
        async def callback(bar):
            received.append(bar)
            data_stream_pipeline.stop()

        await data_stream_pipeline.consume_bars(callback)

        assert len(received) == 1
        assert isinstance(received[0], OHLCVBar)
        assert received[0].symbol == "SOL/USDC"
        assert received[0].close == 142.5


class TestDataStreamPipelineConsumeFeatures:
    @pytest.mark.asyncio
    async def test_consume_features(self, data_stream_pipeline, mock_kafka_consumer):
        feature_data = {
            "type": "features",
            "symbol": "SOL/USDC",
            "features": {"rsi_14": 65.4, "ema_9": 142.3},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }
        msg = KafkaMessage(topic="dats.market.data", value=feature_data)

        async def mock_consume(*args, **kwargs):
            yield msg
            await asyncio.sleep(0.01)

        mock_kafka_consumer.consume = mock_consume

        received = []
        async def callback(symbol, features, ts):
            received.append((symbol, features, ts))
            data_stream_pipeline.stop()

        await data_stream_pipeline.consume_features(callback)

        assert len(received) == 1
        assert received[0][0] == "SOL/USDC"
        assert received[0][1]["rsi_14"] == 65.4


class TestDataStreamPipelineLifecycle:
    def test_stop(self, data_stream_pipeline):
        assert not data_stream_pipeline._stop_event.is_set()
        data_stream_pipeline.stop()
        assert data_stream_pipeline._stop_event.is_set()

    def test_reset(self, data_stream_pipeline):
        data_stream_pipeline.stop()
        assert data_stream_pipeline._stop_event.is_set()
        data_stream_pipeline.reset()
        assert not data_stream_pipeline._stop_event.is_set()

    def test_stop_and_reset_cycle(self, data_stream_pipeline):
        data_stream_pipeline.stop()
        assert data_stream_pipeline._stop_event.is_set()
        data_stream_pipeline.reset()
        assert not data_stream_pipeline._stop_event.is_set()
        data_stream_pipeline.stop()
        assert data_stream_pipeline._stop_event.is_set()
