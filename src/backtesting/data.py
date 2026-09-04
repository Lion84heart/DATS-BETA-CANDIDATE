"""Historical OHLCV data sources for backtesting.

Two sources:

1. **CSV import** — real historical OHLCV data supplied by the caller in
   the standard ``timestamp,open,high,low,close,volume`` format. This is
   literal replay of real market history when the caller has it.

2. **Synthetic generation** — when no historical file is available, bars
   are generated via the existing ``MarketSimulator`` (the same
   geometric-Brownian-motion engine that already drives live paper
   trading's simulated price feed, see market/connectors/simulated.py).
   Several intrabar sub-steps are sampled per bar to produce genuine
   open/high/low/close (unlike the live tick feed's single-price bars),
   with volume synthesized via a simple heuristic (larger moves get more
   volume, a well-known real-market pattern). This is clearly synthetic
   data for backtesting purposes, never presented as real market history.
"""

from __future__ import annotations

import csv
import io
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from simulation.market_sim import MarketSimulator

# Same illustrative starting-price universe as live Paper Trading
# (api/routers/execution.py's _DEFAULT_SEED_PRICES) — duplicated rather
# than imported to avoid a backtesting -> api.routers layering violation.
_DEFAULT_SEED_PRICES: dict[str, float] = {
    "AAPL": 182.50, "MSFT": 335.80, "GOOGL": 128.40, "TSLA": 255.30,
    "NVDA": 465.00, "AMZN": 158.00, "META": 510.00, "AMD": 142.00,
}

_TIMESTAMP_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class HistoricalBar:
    """One OHLCV bar for replay."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


def generate_synthetic_ohlcv(
    symbol: str,
    num_bars: int,
    seed: int | None = None,
    start_price: float | None = None,
    sub_steps: int = 20,
    bar_seconds: float = 86400.0,
    volatility: float = 0.02,
    drift: float = 0.0003,
) -> list[HistoricalBar]:
    """Generate synthetic OHLCV bars via the existing MarketSimulator.

    Args:
        symbol: Symbol to seed a starting price for.
        num_bars: Number of bars to generate.
        seed: Random seed (reproducible runs).
        start_price: Override the default seed price.
        sub_steps: Intrabar samples used to derive open/high/low/close.
        bar_seconds: Duration each bar represents (default: 1 day).
        volatility: Per-bar volatility passed to the GBM engine.
        drift: Per-bar drift passed to the GBM engine.

    Returns:
        Bars in chronological order, oldest first.
    """
    sim = MarketSimulator(seed=seed, default_volatility=volatility, default_drift=drift)
    volume_rng = random.Random(seed)
    current = start_price if start_price is not None else _DEFAULT_SEED_PRICES.get(symbol, 100.0)
    start_ts = time.time() - num_bars * bar_seconds

    bars: list[HistoricalBar] = []
    for i in range(num_bars):
        path = sim.generate_path(
            symbol, current, sub_steps, timestep_days=(bar_seconds / 86400.0) / sub_steps
        )
        prices = path.prices  # sub_steps + 1 values; prices[0] == current
        o, c = prices[0], prices[-1]
        h, l = max(prices), min(prices)  # noqa: E741
        move_pct = abs((c - o) / o) if o else 0.0
        base_volume = volume_rng.uniform(20_000, 80_000)
        volume = max(100.0, base_volume * (1.0 + move_pct * 15.0))

        bars.append(
            HistoricalBar(
                timestamp=start_ts + i * bar_seconds,
                open=o, high=h, low=l, close=c, volume=volume,
            )
        )
        current = c

    return bars


def parse_csv_ohlcv(csv_text: str) -> list[HistoricalBar]:
    """Parse real historical OHLCV data from CSV text.

    Expected columns (case-insensitive): a timestamp column named
    ``timestamp``, ``date``, or ``time`` (epoch seconds or
    YYYY-MM-DD[THH:MM:SS]), plus ``open``, ``high``, ``low``, ``close``,
    and optionally ``volume`` (defaults to 0).

    Args:
        csv_text: Raw CSV content.

    Returns:
        Bars sorted chronologically, oldest first.

    Raises:
        ValueError: If required columns are missing or unparseable.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")
    fields = {name.strip().lower(): name for name in reader.fieldnames}

    ts_col = fields.get("timestamp") or fields.get("date") or fields.get("time")
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in fields]
    if ts_col is None or missing:
        raise ValueError(
            f"CSV missing required columns. Need a timestamp/date/time column and "
            f"{required}; missing: {(['timestamp/date/time'] if ts_col is None else [])+missing}"
        )

    bars: list[HistoricalBar] = []
    for row_num, row in enumerate(reader, start=2):
        try:
            ts = _parse_timestamp(row[ts_col])
            volume_col = fields.get("volume")
            bars.append(
                HistoricalBar(
                    timestamp=ts,
                    open=float(row[fields["open"]]),
                    high=float(row[fields["high"]]),
                    low=float(row[fields["low"]]),
                    close=float(row[fields["close"]]),
                    volume=float(row[volume_col]) if volume_col and row.get(volume_col) else 0.0,
                )
            )
        except (KeyError, ValueError) as e:
            raise ValueError(f"CSV row {row_num} is invalid: {e}") from e

    bars.sort(key=lambda b: b.timestamp)
    return bars


def _parse_timestamp(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty timestamp")
    try:
        return float(raw)
    except ValueError:
        pass
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"unrecognized timestamp format: {raw!r}")
