"""Phase 3 — OHLCV data-integrity validation for historical datasets.

Reuses two existing, unmodified pieces of infrastructure rather than
reimplementing validation from scratch:

  - ``market.schemas.OHLCVBar``'s own Pydantic validators (high >= low,
    strictly positive prices, non-negative volume) — constructing each
    row as an ``OHLCVBar`` *is* a real integrity check, not just a type
    cast; a malformed row raises ``ValidationError`` and is rejected.
  - ``data.quality.DataQualityEngine``'s ``check_completeness`` (gap
    detection against the expected bar interval) and ``detect_outliers``
    (IQR-based price-outlier detection), already used elsewhere in the
    codebase for data-quality reporting.

Neither dependency is modified — both are called exactly as their
existing public interface already allows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pydantic import ValidationError

from data.quality import DataQualityEngine
from market.schemas import OHLCVBar

# pandas Timedelta-compatible frequency strings for each Binance interval.
# "1w"/"1M" are approximated as 7D/30D since pandas Timedelta has no
# calendar-month/week unit of its own — documented, not silently assumed.
_PANDAS_FREQ: dict[str, str] = {
    "1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1D", "3d": "3D", "1w": "7D", "1M": "30D",
}


@dataclass
class IntegrityReport:
    """Full integrity report for one (symbol, interval) historical fetch."""

    symbol: str
    interval: str
    rows_in: int
    rows_valid: int
    rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    duplicate_timestamps: int = 0
    gap_count: int = 0
    outlier_count: int = 0
    is_clean: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "rows_in": self.rows_in, "rows_valid": self.rows_valid,
            "rejected_count": len(self.rejected_rows), "rejected_rows_sample": self.rejected_rows[:10],
            "duplicate_timestamps": self.duplicate_timestamps, "gap_count": self.gap_count,
            "outlier_count": self.outlier_count, "is_clean": self.is_clean, "notes": self.notes,
        }


def validate_klines(
    symbol: str, interval: str, raw_klines: list[list[Any]],
) -> tuple[list[OHLCVBar], IntegrityReport]:
    """Validate raw Binance kline rows.

    Args:
        symbol: Trading symbol the rows belong to.
        interval: Binance interval string, e.g. ``"1h"``.
        raw_klines: Raw kline rows from ``BinanceHistoricalClient.get_klines``.

    Returns:
        ``(clean_bars, report)`` — rows that fail ``OHLCVBar``'s own
        validation (bad high/low relationship, non-positive price,
        negative volume) are rejected and recorded in the report, not
        silently dropped. Duplicate open-timestamps are also skipped
        and counted.
    """
    valid_bars: list[OHLCVBar] = []
    rejected: list[dict[str, Any]] = []
    seen_timestamps: set[int] = set()
    duplicate_count = 0

    for row in raw_klines:
        try:
            open_time_ms = int(row[0])
            if open_time_ms in seen_timestamps:
                duplicate_count += 1
                continue
            seen_timestamps.add(open_time_ms)
            bar = OHLCVBar(
                symbol=symbol, open=float(row[1]), high=float(row[2]),
                low=float(row[3]), close=float(row[4]), volume=float(row[5]),
                timestamp=datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc),
                interval=interval,
            )
            valid_bars.append(bar)
        except (ValidationError, ValueError, TypeError, IndexError) as exc:
            rejected.append({"row": row, "error": str(exc)})

    notes: list[str] = []
    gap_count = 0
    outlier_count = 0
    if valid_bars:
        df = pd.DataFrame(
            {"timestamp": [b.timestamp for b in valid_bars], "close": [b.close for b in valid_bars]}
        ).set_index("timestamp").sort_index()

        engine = DataQualityEngine()
        freq = _PANDAS_FREQ.get(interval, "1h")
        completeness = engine.check_completeness(df, freq)
        gap_count = completeness["gap_count"]
        if gap_count:
            notes.append(f"{gap_count} gap(s) larger than 1.5x the expected {interval} interval detected.")

        outliers = engine.detect_outliers(df["close"], method="iqr")
        outlier_count = len(outliers)
        if outlier_count:
            notes.append(
                f"{outlier_count} close-price outlier(s) flagged via IQR — informational only, "
                "not rejected: real markets have legitimate large moves."
            )

    if rejected:
        notes.append(f"{len(rejected)} row(s) rejected by OHLCVBar's own validation.")
    if duplicate_count:
        notes.append(f"{duplicate_count} duplicate timestamp(s) skipped.")

    report = IntegrityReport(
        symbol=symbol, interval=interval, rows_in=len(raw_klines), rows_valid=len(valid_bars),
        rejected_rows=rejected, duplicate_timestamps=duplicate_count, gap_count=gap_count,
        outlier_count=outlier_count,
        is_clean=(len(rejected) == 0 and duplicate_count == 0 and gap_count == 0),
        notes=notes,
    )
    return valid_bars, report
