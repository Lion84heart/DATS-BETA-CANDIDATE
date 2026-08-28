"""Tests for the FeatureEngine (technical indicator computation)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.data.features import FeatureEngine


class TestFeatureEngineAllFeatureNames:
    def test_all_feature_names(self, feature_engine):
        names = feature_engine.all_feature_names()
        assert len(names) > 0
        assert "rsi_14" in names
        assert "ema_9" in names
        assert "macd" in names
        assert "bb_upper" in names
        assert "return_1m" in names
        assert "atr_14" in names
        assert "adx_14" in names
        assert "z_score" in names


class TestFeatureEngineEmptyData:
    def test_empty_df_returns_none(self, feature_engine, empty_df):
        result = feature_engine.compute_features(empty_df)
        assert all(v is None for v in result.values())

    def test_small_df_some_none(self, feature_engine, small_ohlcv_df):
        result = feature_engine.compute_features(small_ohlcv_df)
        # Some features should be computable with 10 rows
        assert result["return_1m"] is not None
        assert result["rsi_14"] is None  # Needs 15 rows
        assert result["sma_200"] is None  # Needs 200 rows


class TestFeatureEngineReturns:
    def test_return_1m(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["return_1m"])
        assert result["return_1m"] is not None
        last_close = ohlcv_df["close"].iloc[-1]
        prev_close = ohlcv_df["close"].iloc[-2]
        expected = last_close / prev_close - 1
        assert abs(result["return_1m"] - expected) < 1e-10

    def test_return_5m(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["return_5m"])
        assert result["return_5m"] is not None

    def test_return_15m(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["return_15m"])
        assert result["return_15m"] is not None

    def test_return_1h(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["return_1h"])
        assert result["return_1h"] is not None


class TestFeatureEngineRSI:
    def test_rsi_14(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["rsi_14"])
        assert result["rsi_14"] is not None
        assert 0 <= result["rsi_14"] <= 100

    def test_rsi_7(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["rsi_7"])
        assert result["rsi_7"] is not None
        assert 0 <= result["rsi_7"] <= 100

    def test_rsi_too_few_rows(self, feature_engine, small_ohlcv_df):
        result = feature_engine.compute_features(small_ohlcv_df, feature_list=["rsi_14"])
        assert result["rsi_14"] is None


class TestFeatureEngineMACD:
    def test_macd(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(
            ohlcv_df, feature_list=["macd", "macd_signal", "macd_histogram"]
        )
        assert result["macd"] is not None
        assert result["macd_signal"] is not None
        assert result["macd_histogram"] is not None
        # Histogram = MACD - signal
        expected_hist = result["macd"] - result["macd_signal"]
        assert abs(result["macd_histogram"] - expected_hist) < 1e-10


class TestFeatureEngineBollingerBands:
    def test_bb_all(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(
            ohlcv_df,
            feature_list=["bb_upper", "bb_lower", "bb_width", "bb_pct_b"],
        )
        assert result["bb_upper"] is not None
        assert result["bb_lower"] is not None
        assert result["bb_width"] is not None
        assert result["bb_pct_b"] is not None
        assert result["bb_upper"] >= result["bb_lower"]


class TestFeatureEngineEMA:
    def test_ema_9(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["ema_9"])
        assert result["ema_9"] is not None

    def test_ema_21(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["ema_21"])
        assert result["ema_21"] is not None

    def test_ema_50(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["ema_50"])
        assert result["ema_50"] is not None

    def test_ema_not_enough_data(self, feature_engine, small_ohlcv_df):
        result = feature_engine.compute_features(small_ohlcv_df, feature_list=["ema_50"])
        assert result["ema_50"] is None


class TestFeatureEngineSMA:
    def test_sma_20(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["sma_20"])
        assert result["sma_20"] is not None

    def test_sma_50(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["sma_50"])
        assert result["sma_50"] is not None

    def test_sma_200(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["sma_200"])
        assert result["sma_200"] is not None

    def test_sma_not_enough_data(self, feature_engine, small_ohlcv_df):
        result = feature_engine.compute_features(small_ohlcv_df, feature_list=["sma_20"])
        assert result["sma_20"] is None


class TestFeatureEngineVolume:
    def test_relative_volume(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["relative_volume"])
        assert result["relative_volume"] is not None
        assert result["relative_volume"] > 0

    def test_volume_change(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["volume_change"])
        assert result["volume_change"] is not None


class TestFeatureEngineVolatility:
    def test_atr_14(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["atr_14"])
        assert result["atr_14"] is not None
        assert result["atr_14"] > 0

    def test_realized_vol_20(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["realized_vol_20"])
        assert result["realized_vol_20"] is not None
        assert result["realized_vol_20"] >= 0


class TestFeatureEngineStatistical:
    def test_skewness(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["skewness"])
        assert result["skewness"] is not None

    def test_kurtosis(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["kurtosis"])
        assert result["kurtosis"] is not None

    def test_z_score(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["z_score"])
        assert result["z_score"] is not None


class TestFeatureEngineTrend:
    def test_adx_14(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["adx_14"])
        assert result["adx_14"] is not None
        assert 0 <= result["adx_14"] <= 100

    def test_plus_di(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["plus_di"])
        assert result["plus_di"] is not None

    def test_minus_di(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["minus_di"])
        assert result["minus_di"] is not None


class TestFeatureEnginePricePosition:
    def test_dist_from_vwap(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["dist_from_vwap"])
        assert result["dist_from_vwap"] is not None

    def test_dist_from_ema50(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["dist_from_ema50"])
        assert result["dist_from_ema50"] is not None


class TestFeatureEngineFullComputation:
    def test_all_features_computed(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df)
        # With 200 rows, most features should be computable
        assert result["rsi_14"] is not None
        assert result["macd"] is not None
        assert result["ema_9"] is not None
        assert result["sma_20"] is not None
        assert result["sma_200"] is not None
        assert result["atr_14"] is not None
        assert result["return_1m"] is not None

    def test_unknown_feature_returns_none(self, feature_engine, ohlcv_df):
        result = feature_engine.compute_features(ohlcv_df, feature_list=["nonexistent_feature"])
        assert result["nonexistent_feature"] is None

    def test_missing_columns(self, feature_engine):
        df = pd.DataFrame({"only_col": [1, 2, 3]})
        result = feature_engine.compute_features(df)
        assert all(v is None for v in result.values())


class TestFeatureEngineHelpers:
    def test_rsi_helper_directly(self, feature_engine):
        series = pd.Series([100, 101, 102, 101, 103, 104, 103, 105, 106, 107, 106, 108, 109, 110, 111])
        rsi = feature_engine._rsi(series, 14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_macd_helper_directly(self, feature_engine):
        series = pd.Series(range(100, 150))
        macd, signal, hist = feature_engine._macd(series)
        assert macd is not None
        assert signal is not None
        assert hist is not None

    def test_bollinger_bands_helper(self, feature_engine):
        series = pd.Series([100 + i for i in range(30)])
        upper, lower, width, pct_b = feature_engine._bollinger_bands(series)
        assert upper is not None
        assert lower is not None
        assert width is not None
        assert 0 <= pct_b <= 1

    def test_atr_helper(self, feature_engine):
        high = pd.Series([101 + i for i in range(20)])
        low = pd.Series([99 + i for i in range(20)])
        close = pd.Series([100 + i for i in range(20)])
        atr = feature_engine._atr(high, low, close, 14)
        assert atr is not None
        assert atr > 0

    def test_adx_helper(self, feature_engine):
        high = pd.Series([101 + i * 0.5 for i in range(50)])
        low = pd.Series([99 + i * 0.3 for i in range(50)])
        close = pd.Series([100 + i * 0.4 for i in range(50)])
        adx, plus_di, minus_di = feature_engine._adx(high, low, close, 14)
        assert adx is not None
        assert plus_di is not None
        assert minus_di is not None
