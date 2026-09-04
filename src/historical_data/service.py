"""Phase 3 — Historical Data Service.

The single entry point this phase was asked to build: fetch (Binance,
cached), validate, and convert real historical OHLCV into the exact
``backtesting.data.HistoricalBar`` shape the frozen
``backtesting.engine.BacktestEngine`` already consumes from its
synthetic and CSV-import sources — so a real dataset feeds the
existing Backtest Engine with zero changes to that engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backtesting.data import HistoricalBar
from historical_data.binance_client import BinanceHistoricalClient
from historical_data.cache import HistoricalDataCache, cache_key
from historical_data.integrity import IntegrityReport, validate_klines
from market.schemas import OHLCVBar

_SUPPORTED_SOURCES = ("binance",)


@dataclass
class HistoricalDataset:
    """Everything one ``get_ohlcv`` call produces."""

    bars: list[HistoricalBar]
    integrity: IntegrityReport
    cache_hit: bool
    manifest: dict[str, Any]


def _to_historical_bars(ohlcv_bars: list[OHLCVBar]) -> list[HistoricalBar]:
    return [
        HistoricalBar(
            timestamp=b.timestamp.timestamp(), open=b.open, high=b.high,
            low=b.low, close=b.close, volume=b.volume,
        )
        for b in ohlcv_bars
    ]


class HistoricalDataService:
    """Fetch, cache, validate, and convert real historical OHLCV."""

    def __init__(self, cache: HistoricalDataCache | None = None) -> None:
        self.cache = cache or HistoricalDataCache()

    async def get_ohlcv(
        self, symbol: str, interval: str, start_time_ms: int, end_time_ms: int,
        source: str = "binance",
    ) -> HistoricalDataset:
        """Return a ready-to-backtest dataset for ``symbol``/``interval``
        over ``[start_time_ms, end_time_ms)``.

        Checks the on-disk cache first; on a miss, fetches live from the
        given source, validates the raw rows, and caches the result
        (raw rows + a checksummed manifest) before returning.
        """
        if source not in _SUPPORTED_SOURCES:
            raise ValueError(f"Unsupported historical data source: {source!r}. Supported: {_SUPPORTED_SOURCES}")

        key = cache_key(source, symbol, interval, start_time_ms, end_time_ms)
        cached = self.cache.get(key)
        if cached is not None:
            raw_klines, manifest = cached
            cache_hit = True
        else:
            async with BinanceHistoricalClient() as client:
                raw_klines = await client.get_klines(symbol, interval, start_time_ms, end_time_ms)
            manifest = self.cache.put(key, source, symbol, interval, start_time_ms, end_time_ms, raw_klines)
            cache_hit = False

        ohlcv_bars, integrity = validate_klines(symbol, interval, raw_klines)
        bars = _to_historical_bars(ohlcv_bars)
        return HistoricalDataset(bars=bars, integrity=integrity, cache_hit=cache_hit, manifest=manifest.to_dict())
