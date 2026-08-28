"""Tests for market data Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.market.schemas import (
    OHLCVBar,
    OrderBookEntry,
    OrderBookSnapshot,
    PriceTick,
    SentimentReading,
    TradeEvent,
)


class TestPriceTick:
    def test_valid_tick(self, price_tick):
        assert price_tick.symbol == "SOL/USDC"
        assert price_tick.price == 142.5
        assert price_tick.volume == 1_000_000.0
        assert price_tick.source == "jupiter"

    def test_price_must_be_positive(self):
        with pytest.raises(ValidationError):
            PriceTick(symbol="SOL/USDC", price=-1.0)

    def test_default_timestamp(self):
        tick = PriceTick(symbol="X", price=1.0)
        assert tick.timestamp is not None
        assert tick.timestamp.tzinfo is not None

    def test_timestamp_from_string(self):
        tick = PriceTick(symbol="X", price=1.0, timestamp="2024-01-01T00:00:00Z")
        assert tick.timestamp.year == 2024

    def test_volume_defaults_to_zero(self):
        tick = PriceTick(symbol="X", price=1.0)
        assert tick.volume == 0.0


class TestOrderBookEntry:
    def test_valid_entry(self, order_book_entry):
        assert order_book_entry.price == 142.5
        assert order_book_entry.size == 10.0
        assert order_book_entry.side == "bid"

    def test_side_validation(self):
        with pytest.raises(ValidationError):
            OrderBookEntry(price=1.0, size=1.0, side="invalid")


class TestOrderBookSnapshot:
    def test_valid_snapshot(self, order_book_snapshot):
        assert order_book_snapshot.symbol == "SOL/USDC"
        assert len(order_book_snapshot.bids) == 2
        assert len(order_book_snapshot.asks) == 2

    def test_empty_orderbook(self):
        snap = OrderBookSnapshot(symbol="X")
        assert snap.bids == []
        assert snap.asks == []


class TestTradeEvent:
    def test_valid_trade(self, trade_event):
        assert trade_event.symbol == "SOL/USDC"
        assert trade_event.price == 142.5
        assert trade_event.side == "buy"
        assert trade_event.signature == "abc123"

    def test_side_validation(self):
        with pytest.raises(ValidationError):
            TradeEvent(symbol="X", price=1.0, size=1.0, side="invalid")


class TestSentimentReading:
    def test_valid_reading(self):
        reading = SentimentReading(source="twitter", score=0.75, text_preview="Bullish on SOL")
        assert reading.source == "twitter"
        assert reading.score == 0.75

    def test_score_range(self):
        with pytest.raises(ValidationError):
            SentimentReading(source="x", score=1.5)
        with pytest.raises(ValidationError):
            SentimentReading(source="x", score=-1.5)


class TestOHLCVBar:
    def test_valid_bar(self, ohlcv_bar):
        assert ohlcv_bar.symbol == "SOL/USDC"
        assert ohlcv_bar.open == 140.0
        assert ohlcv_bar.high == 145.0
        assert ohlcv_bar.low == 139.0
        assert ohlcv_bar.close == 142.5
        assert ohlcv_bar.interval == "1m"

    def test_high_must_be_ge_low(self):
        with pytest.raises(ValidationError):
            OHLCVBar(
                symbol="X",
                open=100.0,
                high=90.0,
                low=95.0,
                close=92.0,
                volume=100.0,
            )

    def test_prices_must_be_positive(self):
        with pytest.raises(ValidationError):
            OHLCVBar(
                symbol="X",
                open=-1.0,
                high=100.0,
                low=99.0,
                close=99.5,
                volume=100.0,
            )

    def test_default_interval(self):
        bar = OHLCVBar(
            symbol="X",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=100.0,
        )
        assert bar.interval == "1m"
