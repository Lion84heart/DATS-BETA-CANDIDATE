"""DATS — Kafka Streaming Integration.

Publishes and consumes market-data events (ticks, bars, features) via
the M1 Kafka producer/consumer infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from infra.kafka_client import (
    MARKET_DATA,
    KafkaConsumer,
    KafkaProducer,
)
from market.schemas import OHLCVBar, PriceTick

logger = logging.getLogger(__name__)


class DataStreamPipeline:
    """Kafka-based streaming pipeline for market data.

    Publishes ticks, bars, and feature vectors to Kafka topics and
    provides async consumer loops with graceful shutdown.

    Usage::

        pipeline = DataStreamPipeline(producer, consumer)
        await pipeline.publish_tick(tick)

        # Consume
        async def handle_tick(msg):
            print(msg.value)

        await pipeline.consume_ticks(handle_tick)
    """

    def __init__(
        self,
        producer: KafkaProducer,
        consumer: KafkaConsumer,
    ) -> None:
        self.producer: KafkaProducer = producer
        self.consumer: KafkaConsumer = consumer
        self._stop_event: asyncio.Event = asyncio.Event()

    # -- Publishing ----------------------------------------------------------

    async def publish_tick(self, tick: PriceTick) -> dict[str, Any]:
        """Publish a ``PriceTick`` to the market-data topic.

        Args:
            tick: The price tick to publish.

        Returns:
            Send metadata dict.
        """
        payload = {
            "type": "tick",
            "symbol": tick.symbol,
            "price": tick.price,
            "volume": tick.volume,
            "timestamp": tick.timestamp.isoformat(),
            "source": tick.source,
        }
        result = await self.producer.send(
            MARKET_DATA,
            value=payload,
            key=tick.symbol,
        )
        logger.debug("Published tick for %s", tick.symbol)
        return result

    async def publish_bar(self, bar: OHLCVBar) -> dict[str, Any]:
        """Publish an ``OHLCVBar`` to the market-data topic.

        Args:
            bar: The OHLCV bar to publish.

        Returns:
            Send metadata dict.
        """
        payload = {
            "type": "bar",
            "symbol": bar.symbol,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "timestamp": bar.timestamp.isoformat(),
            "interval": bar.interval,
        }
        result = await self.producer.send(
            MARKET_DATA,
            value=payload,
            key=bar.symbol,
        )
        logger.debug("Published bar for %s", bar.symbol)
        return result

    async def publish_features(
        self,
        symbol: str,
        features: dict[str, float | None],
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """Publish a feature vector to the market-data topic.

        Args:
            symbol: Trading symbol.
            features: Dict of feature name → value.
            timestamp: Optional ISO timestamp (defaults to now).

        Returns:
            Send metadata dict.
        """
        from datetime import datetime, timezone

        if timestamp is None:
            timestamp = datetime.now(timezone.utc).isoformat()

        # Filter out None values and make JSON-safe
        clean_features = {
            k: (v if v is not None else "nan")
            for k, v in features.items()
        }

        payload = {
            "type": "features",
            "symbol": symbol,
            "features": clean_features,
            "timestamp": timestamp,
        }
        result = await self.producer.send(
            MARKET_DATA,
            value=payload,
            key=symbol,
        )
        logger.debug("Published features for %s (%d features)", symbol, len(features))
        return result

    # -- Consumption ---------------------------------------------------------

    async def consume_ticks(
        self,
        callback: Callable[[PriceTick], Awaitable[None]],
        timeout_ms: int = 1000,
    ) -> None:
        """Consume price-tick messages and invoke *callback* for each.

        Runs until ``stop()`` is called.

        Args:
            callback: Async function receiving a ``PriceTick``.
            timeout_ms: Poll timeout in milliseconds.
        """
        logger.info("Tick consumer loop started.")
        try:
            async for msg in self.consumer.consume(timeout_ms=timeout_ms):
                if self._stop_event.is_set():
                    break
                try:
                    if isinstance(msg.value, dict) and msg.value.get("type") == "tick":
                        tick = PriceTick(
                            symbol=msg.value["symbol"],
                            price=msg.value["price"],
                            volume=msg.value.get("volume", 0.0),
                            timestamp=msg.value["timestamp"],
                            source=msg.value.get("source", "kafka"),
                        )
                        await callback(tick)
                except Exception as exc:
                    logger.error("Error processing tick message: %s", exc)
        except Exception as exc:
            logger.error("Tick consumer loop error: %s", exc)
        finally:
            logger.info("Tick consumer loop exited.")

    async def consume_bars(
        self,
        callback: Callable[[OHLCVBar], Awaitable[None]],
        timeout_ms: int = 1000,
    ) -> None:
        """Consume OHLCV bar messages and invoke *callback* for each.

        Runs until ``stop()`` is called.

        Args:
            callback: Async function receiving an ``OHLCVBar``.
            timeout_ms: Poll timeout in milliseconds.
        """
        logger.info("Bar consumer loop started.")
        try:
            async for msg in self.consumer.consume(timeout_ms=timeout_ms):
                if self._stop_event.is_set():
                    break
                try:
                    if isinstance(msg.value, dict) and msg.value.get("type") == "bar":
                        bar = OHLCVBar(
                            symbol=msg.value["symbol"],
                            open=msg.value["open"],
                            high=msg.value["high"],
                            low=msg.value["low"],
                            close=msg.value["close"],
                            volume=msg.value.get("volume", 0.0),
                            timestamp=msg.value["timestamp"],
                            interval=msg.value.get("interval", "1m"),
                        )
                        await callback(bar)
                except Exception as exc:
                    logger.error("Error processing bar message: %s", exc)
        except Exception as exc:
            logger.error("Bar consumer loop error: %s", exc)
        finally:
            logger.info("Bar consumer loop exited.")

    async def consume_features(
        self,
        callback: Callable[[str, dict[str, Any], str], Awaitable[None]],
        timeout_ms: int = 1000,
    ) -> None:
        """Consume feature messages and invoke *callback* for each.

        Runs until ``stop()`` is called.

        Args:
            callback: Async function receiving (symbol, features, timestamp).
            timeout_ms: Poll timeout in milliseconds.
        """
        logger.info("Feature consumer loop started.")
        try:
            async for msg in self.consumer.consume(timeout_ms=timeout_ms):
                if self._stop_event.is_set():
                    break
                try:
                    if isinstance(msg.value, dict) and msg.value.get("type") == "features":
                        symbol = msg.value["symbol"]
                        features = msg.value.get("features", {})
                        timestamp = msg.value.get("timestamp", "")
                        await callback(symbol, features, timestamp)
                except Exception as exc:
                    logger.error("Error processing feature message: %s", exc)
        except Exception as exc:
            logger.error("Feature consumer loop error: %s", exc)
        finally:
            logger.info("Feature consumer loop exited.")

    # -- Lifecycle -----------------------------------------------------------

    def stop(self) -> None:
        """Signal all consumer loops to stop gracefully."""
        logger.info("Stop signal received for DataStreamPipeline.")
        self._stop_event.set()

    def reset(self) -> None:
        """Reset the stop event (for re-starting consumption)."""
        self._stop_event.clear()
