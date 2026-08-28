"""DATS — Feature Engineering Engine.

Computes technical indicators and statistical features from OHLCV DataFrames.
Uses lazy evaluation: only requested features are computed.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FeatureEngine:
    """Computes technical indicator features from OHLCV data.

    Usage::

        engine = FeatureEngine()
        features = engine.compute_features(ohlcv_df)
        # features → {"rsi_14": 65.4, "ema_9": 142.3, ...}
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def compute_features(
        self,
        ohlcv_df: pd.DataFrame,
        feature_list: list[str] | None = None,
    ) -> dict[str, float | None]:
        """Compute features from an OHLCV DataFrame.

        Args:
            ohlcv_df: DataFrame with columns ``open``, ``high``, ``low``,
                ``close``, ``volume``, indexed by timestamp.
            feature_list: Optional list of specific feature names to compute.
                If ``None``, all features are computed.

        Returns:
            Dict mapping feature name → value (or ``None`` if not computable).
        """
        self._cache = {}

        if ohlcv_df.empty or len(ohlcv_df) < 2:
            logger.warning("Empty or insufficient OHLCV data for feature computation.")
            return self._empty_result()

        df = ohlcv_df.copy()
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(df.columns.str.lower())
        if missing:
            logger.warning("Missing OHLCV columns: %s", missing)
            return self._empty_result()

        # Normalise column names to lowercase
        df.columns = df.columns.str.lower()

        all_features: dict[str, float | None] = {}

        # Determine which features to compute
        features_to_compute = feature_list or self.all_feature_names()

        for feat in features_to_compute:
            try:
                value = self._compute_single_feature(feat, df)
                all_features[feat] = value
            except Exception as exc:
                logger.debug("Feature %s could not be computed: %s", feat, exc)
                all_features[feat] = None

        return all_features

    @staticmethod
    def all_feature_names() -> list[str]:
        """Return the list of all supported feature names."""
        return [
            # Returns
            "return_1m",
            "return_5m",
            "return_15m",
            "return_1h",
            # RSI
            "rsi_14",
            "rsi_7",
            # MACD
            "macd",
            "macd_signal",
            "macd_histogram",
            # Bollinger Bands
            "bb_upper",
            "bb_lower",
            "bb_width",
            "bb_pct_b",
            # EMA
            "ema_9",
            "ema_21",
            "ema_50",
            # SMA
            "sma_20",
            "sma_50",
            "sma_200",
            # Volume
            "relative_volume",
            "volume_change",
            # Volatility
            "atr_14",
            "realized_vol_20",
            # Statistical
            "skewness",
            "kurtosis",
            "z_score",
            # Trend
            "adx_14",
            "plus_di",
            "minus_di",
            # Price position
            "dist_from_vwap",
            "dist_from_ema50",
        ]

    def _empty_result(self) -> dict[str, None]:
        return {name: None for name in self.all_feature_names()}

    # ------------------------------------------------------------------
    # Per-feature computation
    # ------------------------------------------------------------------

    def _compute_single_feature(
        self,
        feature: str,
        df: pd.DataFrame,
    ) -> float | None:
        """Compute a single feature by name."""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # -- Returns ---------------------------------------------------
        if feature == "return_1m":
            if len(close) < 2:
                return None
            return float(close.iloc[-1] / close.iloc[-2] - 1)

        if feature == "return_5m":
            if len(close) < 6:
                return None
            return float(close.iloc[-1] / close.iloc[-6] - 1)

        if feature == "return_15m":
            if len(close) < 16:
                return None
            return float(close.iloc[-1] / close.iloc[-16] - 1)

        if feature == "return_1h":
            if len(close) < 61:
                return None
            return float(close.iloc[-1] / close.iloc[-61] - 1)

        # -- RSI -------------------------------------------------------
        if feature == "rsi_14":
            return self._rsi(close, 14)

        if feature == "rsi_7":
            return self._rsi(close, 7)

        # -- MACD ------------------------------------------------------
        if feature in ("macd", "macd_signal", "macd_histogram"):
            macd_line, signal_line, histogram = self._macd(close)
            if feature == "macd":
                return macd_line
            if feature == "macd_signal":
                return signal_line
            return histogram

        # -- Bollinger Bands -------------------------------------------
        if feature in ("bb_upper", "bb_lower", "bb_width", "bb_pct_b"):
            upper, lower, width, pct_b = self._bollinger_bands(close)
            if feature == "bb_upper":
                return upper
            if feature == "bb_lower":
                return lower
            if feature == "bb_width":
                return width
            return pct_b

        # -- EMA -------------------------------------------------------
        if feature == "ema_9":
            return self._ema(close, 9)
        if feature == "ema_21":
            return self._ema(close, 21)
        if feature == "ema_50":
            return self._ema(close, 50)

        # -- SMA -------------------------------------------------------
        if feature == "sma_20":
            return self._sma(close, 20)
        if feature == "sma_50":
            return self._sma(close, 50)
        if feature == "sma_200":
            return self._sma(close, 200)

        # -- Volume ----------------------------------------------------
        if feature == "relative_volume":
            if len(volume) < 20:
                return None
            avg_vol = volume.iloc[-20:].mean()
            if avg_vol == 0:
                return None
            return float(volume.iloc[-1] / avg_vol)

        if feature == "volume_change":
            if len(volume) < 2:
                return None
            prev = volume.iloc[-2]
            if prev == 0:
                return None
            return float(volume.iloc[-1] / prev - 1)

        # -- Volatility ------------------------------------------------
        if feature == "atr_14":
            return self._atr(high, low, close, 14)

        if feature == "realized_vol_20":
            if len(close) < 21:
                return None
            returns = close.pct_change().dropna().iloc[-20:]
            if len(returns) < 2:
                return None
            return float(returns.std() * np.sqrt(len(returns)))

        # -- Statistical -------------------------------------------------
        if feature == "skewness":
            if len(close) < 10:
                return None
            return float(close.iloc[-20:].skew()) if len(close) >= 20 else float(close.skew())

        if feature == "kurtosis":
            if len(close) < 10:
                return None
            return float(close.iloc[-20:].kurtosis()) if len(close) >= 20 else float(close.kurtosis())

        if feature == "z_score":
            if len(close) < 20:
                return None
            window = close.iloc[-20:]
            mean = window.mean()
            std = window.std()
            if std == 0 or pd.isna(std):
                return None
            return float((close.iloc[-1] - mean) / std)

        # -- Trend (ADX) -----------------------------------------------
        if feature in ("adx_14", "plus_di", "minus_di"):
            adx, plus_di, minus_di = self._adx(high, low, close, 14)
            if feature == "adx_14":
                return adx
            if feature == "plus_di":
                return plus_di
            return minus_di

        # -- Price position --------------------------------------------
        if feature == "dist_from_vwap":
            return self._dist_from_vwap(df)

        if feature == "dist_from_ema50":
            if len(close) < 50:
                return None
            ema50_val = close.ewm(span=50, adjust=False).mean().iloc[-1]
            return float((close.iloc[-1] - ema50_val) / ema50_val)

        # Unknown feature
        logger.warning("Unknown feature requested: %s", feature)
        return None

    # ------------------------------------------------------------------
    # Indicator helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rsi(series: pd.Series, period: int) -> float | None:
        if len(series) < period + 1:
            return None
        delta = series.diff().dropna()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _macd(
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> tuple[float | None, float | None, float | None]:
        if len(series) < slow + signal:
            return None, None, None
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return (
            float(macd_line.iloc[-1]),
            float(signal_line.iloc[-1]),
            float(histogram.iloc[-1]),
        )

    @staticmethod
    def _bollinger_bands(
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        if len(series) < period:
            return None, None, None, None
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + std_dev * std
        lower = sma - std_dev * std
        width = (upper - lower) / sma
        # %B = (close - lower) / (upper - lower)
        last_close = series.iloc[-1]
        last_upper = upper.iloc[-1]
        last_lower = lower.iloc[-1]
        band_range = last_upper - last_lower
        pct_b = (last_close - last_lower) / band_range if band_range != 0 else 0.5
        return (
            float(upper.iloc[-1]),
            float(lower.iloc[-1]),
            float(width.iloc[-1]),
            float(pct_b),
        )

    @staticmethod
    def _ema(series: pd.Series, span: int) -> float | None:
        if len(series) < span:
            return None
        return float(series.ewm(span=span, adjust=False).mean().iloc[-1])

    @staticmethod
    def _sma(series: pd.Series, window: int) -> float | None:
        if len(series) < window:
            return None
        return float(series.rolling(window=window).mean().iloc[-1])

    @staticmethod
    def _atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> float | None:
        if len(close) < period + 1:
            return None
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
        return float(atr.iloc[-1])

    @staticmethod
    def _adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> tuple[float | None, float | None, float | None]:
        if len(close) < period * 2 + 1:
            return None, None, None

        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
        plus_di = 100.0 * (plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
        minus_di = 100.0 * (minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr)
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100.0
        adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()

        return (
            float(adx.iloc[-1]),
            float(plus_di.iloc[-1]),
            float(minus_di.iloc[-1]),
        )

    @staticmethod
    def _dist_from_vwap(df: pd.DataFrame) -> float | None:
        if len(df) < 2:
            return None
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
        last_vwap = vwap.iloc[-1]
        if last_vwap == 0 or pd.isna(last_vwap):
            return None
        return float((df["close"].iloc[-1] - last_vwap) / last_vwap)
