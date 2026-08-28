"""DATS — Market Data Connectors.

Provides Pydantic schemas, abstract base connectors, and concrete
implementations for Jupiter, CoinGecko, and Solana RPC APIs.
"""

from market.base_connector import BaseDataConnector
from market.schemas import (
    OHLCVBar,
    OrderBookEntry,
    OrderBookSnapshot,
    PriceTick,
    SentimentReading,
    TradeEvent,
)

__all__ = [
    "BaseDataConnector",
    "PriceTick",
    "OrderBookEntry",
    "OrderBookSnapshot",
    "TradeEvent",
    "SentimentReading",
    "OHLCVBar",
]
