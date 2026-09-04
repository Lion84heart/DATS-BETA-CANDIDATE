"""Phase 3 — on-disk cache and reproducible-dataset store for historical OHLCV.

Persisted under the same mounted ``./data`` volume every other durable
piece of this app's state already lives in (``data/decisions.db``,
etc.), so cached datasets survive a container restart exactly like
everything else.

A disk-backed, checksummed store was chosen over the app's existing
Redis cache (``infra.redis_client.RedisManager``, already used
elsewhere) specifically because Objective 9 ("produce reproducible
research datasets") needs the exact same bytes to still exist later,
not just for as long as a TTL keeps them warm. Redis remains the right
tool for hot, short-lived state; a historical dataset that a research
report cites is a durable artifact, so it gets a durable store.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CACHE_DIR = Path("data/historical_cache")


@dataclass
class DatasetManifest:
    """Reproducibility metadata for one cached historical fetch."""

    source: str
    symbol: str
    interval: str
    start_time_ms: int
    end_time_ms: int
    row_count: int
    sha256: str
    fetched_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def cache_key(source: str, symbol: str, interval: str, start_time_ms: int, end_time_ms: int) -> str:
    return f"{source}_{symbol.upper()}_{interval}_{start_time_ms}_{end_time_ms}"


def _checksum(raw_klines: list[list[Any]]) -> str:
    payload = json.dumps(raw_klines, sort_keys=False, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class HistoricalDataCache:
    """One JSON file per (source, symbol, interval, start, end) key, plus
    a manifest recording a SHA-256 checksum and fetch metadata."""

    def __init__(self, cache_dir: Path | str = _DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.manifest.json"

    def get(self, key: str) -> tuple[list[list[Any]], DatasetManifest] | None:
        """Return the cached ``(raw_klines, manifest)`` for ``key``, or
        ``None`` on a miss. A checksum mismatch (corrupted/edited cache
        file) is also treated as a miss, never returned as if valid."""
        data_path, manifest_path = self._paths(key)
        if not data_path.exists() or not manifest_path.exists():
            return None
        try:
            raw_klines = json.loads(data_path.read_text(encoding="utf-8"))
            manifest = DatasetManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
            if _checksum(raw_klines) != manifest.sha256:
                return None
            return raw_klines, manifest
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def put(
        self, key: str, source: str, symbol: str, interval: str,
        start_time_ms: int, end_time_ms: int, raw_klines: list[list[Any]],
    ) -> DatasetManifest:
        data_path, manifest_path = self._paths(key)
        manifest = DatasetManifest(
            source=source, symbol=symbol, interval=interval,
            start_time_ms=start_time_ms, end_time_ms=end_time_ms,
            row_count=len(raw_klines), sha256=_checksum(raw_klines), fetched_at=time.time(),
        )
        data_path.write_text(json.dumps(raw_klines), encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return manifest
