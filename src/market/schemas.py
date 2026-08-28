"""DATS — Market Data Pydantic v2 Schemas.

Defines the core data models used across market-data ingestion,
feature engineering, and streaming pipelines.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PriceTick(BaseModel):
    """A single price tick / quote for a token pair."""

    symbol: str = Field(..., description="Trading symbol, e.g. 'SOL/USDC'.")
    price: float = Field(..., gt=0, description="Last traded price.")
    volume: float = Field(default=0.0, ge=0, description="24h volume or tick volume.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the tick.",
    )
    source: str = Field(default="unknown", description="Data source name, e.g. 'jupiter'.")

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class OrderBookEntry(BaseModel):
    """A single bid or ask entry in an order book."""

    price: float = Field(..., gt=0, description="Order price.")
    size: float = Field(..., gt=0, description="Order size / quantity.")
    side: Literal["bid", "ask"] = Field(..., description="Order side.")


class OrderBookSnapshot(BaseModel):
    """Full order-book snapshot at a point in time."""

    symbol: str = Field(..., description="Trading symbol.")
    bids: list[OrderBookEntry] = Field(default_factory=list, description="Bid entries.")
    asks: list[OrderBookEntry] = Field(default_factory=list, description="Ask entries.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the snapshot.",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class TradeEvent(BaseModel):
    """Individual trade / fill event."""

    symbol: str = Field(..., description="Trading symbol.")
    price: float = Field(..., gt=0, description="Trade price.")
    size: float = Field(..., gt=0, description="Trade size.")
    side: Literal["buy", "sell"] = Field(..., description="Taker side.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the trade.",
    )
    signature: str | None = Field(
        default=None, description="On-chain transaction signature.",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class SentimentReading(BaseModel):
    """A sentiment score from a text source (social, news, etc.)."""

    source: str = Field(..., description="Source name, e.g. 'twitter'.")
    score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment score from -1 to +1.")
    text_preview: str = Field(default="", description="Truncated text preview.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the reading.",
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class OHLCVBar(BaseModel):
    """An OHLCV candlestick bar."""

    symbol: str = Field(..., description="Trading symbol.")
    open: float = Field(..., gt=0, description="Open price.")
    high: float = Field(..., gt=0, description="High price.")
    low: float = Field(..., gt=0, description="Low price.")
    close: float = Field(..., gt=0, description="Close price.")
    volume: float = Field(..., ge=0, description="Volume.")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Bar start timestamp (UTC).",
    )
    interval: str = Field(default="1m", description="Bar interval, e.g. '1m', '5m', '1h'.")

    @field_validator("high")
    @classmethod
    def _high_ge_low(cls, value: float, info) -> float:
        data = info.data
        low = data.get("low")
        if low is not None and value < low:
            raise ValueError("high must be >= low")
        return value

    @field_validator("low")
    @classmethod
    def _low_le_high(cls, value: float, info) -> float:
        data = info.data
        high = data.get("high")
        if high is not None and value > high:
            raise ValueError("low must be <= high")
        return value

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_utc(cls, value: datetime | str) -> datetime:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
