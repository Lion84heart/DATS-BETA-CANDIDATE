"""Phase 2 — Market Regime detection (research-only).

Classifies each bar of a historical OHLCV series into one of five
regimes, using only close prices already present in the (frozen)
``backtesting.data.HistoricalBar`` series — no new indicator or
strategy is introduced; this is market classification, not a trading
signal.

Method (fully causal — every bar's label uses only bars up to and
including itself, so a backtest replaying these labels bar-by-bar never
sees the future):

1. **Trend** — trailing N-bar return (``close[t] / close[t-N] - 1``).
2. **Realized volatility** — stdev of 1-bar returns over the trailing
   N bars.
3. Both are z-scored against their own trailing history (a longer
   baseline window, strictly before the current bar) so the thresholds
   adapt to each symbol's own scale rather than using one hardcoded
   absolute number across very different price series.
4. **Volatility takes precedence over trend**: a bar with unusually
   high or low realized volatility relative to its own recent history
   is labeled High/Low Volatility regardless of trend direction — in a
   volatility extreme, a "trend" reading is typically noise, not signal.
   Only bars with unremarkable volatility are further classified by
   trend into Trending Bull / Trending Bear / Sideways.
5. Bars without enough trailing history yet (the first
   ``TREND_LOOKBACK + BASELINE_WINDOW`` or so bars of a run) default to
   Sideways — a neutral label, not a guess.
"""

from __future__ import annotations

from statistics import mean, pstdev

from backtesting.data import HistoricalBar

TRENDING_BULL = "TRENDING_BULL"
TRENDING_BEAR = "TRENDING_BEAR"
SIDEWAYS = "SIDEWAYS"
HIGH_VOLATILITY = "HIGH_VOLATILITY"
LOW_VOLATILITY = "LOW_VOLATILITY"

REGIMES: tuple[str, ...] = (
    TRENDING_BULL, TRENDING_BEAR, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY,
)

TREND_LOOKBACK = 20
VOL_LOOKBACK = 20
BASELINE_WINDOW = 100
MIN_BASELINE_SAMPLES = 10
VOL_Z_THRESHOLD = 1.0
TREND_Z_THRESHOLD = 0.5


def detect_regimes(bars: list[HistoricalBar]) -> list[str]:
    """Return one regime label per bar, aligned 1:1 with ``bars``.

    Args:
        bars: Historical OHLCV bars, oldest first.

    Returns:
        List of regime labels (see module constants), same length as
        ``bars``. Causal: label[i] depends only on bars[0..i].
    """
    closes = [b.close for b in bars]
    n = len(closes)

    trend_return: list[float | None] = [None] * n
    realized_vol: list[float | None] = [None] * n
    for i in range(n):
        if i >= TREND_LOOKBACK:
            base = closes[i - TREND_LOOKBACK]
            trend_return[i] = (closes[i] - base) / base if base else 0.0
        if i >= VOL_LOOKBACK:
            rets = [
                (closes[j] - closes[j - 1]) / closes[j - 1]
                for j in range(i - VOL_LOOKBACK + 1, i + 1)
                if closes[j - 1]
            ]
            realized_vol[i] = pstdev(rets) if len(rets) > 1 else 0.0

    regimes: list[str] = [SIDEWAYS] * n
    for i in range(n):
        tr, vol = trend_return[i], realized_vol[i]
        if tr is None or vol is None:
            continue  # not enough lookback yet -> default Sideways

        lo = max(0, i - BASELINE_WINDOW)
        trend_hist = [v for v in trend_return[lo:i] if v is not None]
        vol_hist = [v for v in realized_vol[lo:i] if v is not None]
        if len(trend_hist) < MIN_BASELINE_SAMPLES or len(vol_hist) < MIN_BASELINE_SAMPLES:
            continue  # not enough baseline history yet -> default Sideways

        vol_mean, vol_std = mean(vol_hist), pstdev(vol_hist)
        trend_mean, trend_std = mean(trend_hist), pstdev(trend_hist)
        vol_z = (vol - vol_mean) / vol_std if vol_std > 1e-12 else 0.0
        trend_z = (tr - trend_mean) / trend_std if trend_std > 1e-12 else 0.0

        if vol_z > VOL_Z_THRESHOLD:
            regimes[i] = HIGH_VOLATILITY
        elif vol_z < -VOL_Z_THRESHOLD:
            regimes[i] = LOW_VOLATILITY
        elif trend_z > TREND_Z_THRESHOLD:
            regimes[i] = TRENDING_BULL
        elif trend_z < -TREND_Z_THRESHOLD:
            regimes[i] = TRENDING_BEAR
        else:
            regimes[i] = SIDEWAYS

    return regimes


def time_in_regime_pct(regimes: list[str]) -> dict[str, float]:
    """Percentage of bars spent in each regime."""
    if not regimes:
        return {r: 0.0 for r in REGIMES}
    n = len(regimes)
    return {r: round(regimes.count(r) / n * 100.0, 2) for r in REGIMES}
