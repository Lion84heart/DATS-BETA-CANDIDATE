"""Tests for the DataQualityEngine and DataQualityReport."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.data.quality import DataQualityEngine, DataQualityReport


class TestDataQualityReport:
    def test_default_report(self):
        report = DataQualityReport()
        assert report.summary == ""
        assert report.checks_passed == 0
        assert report.checks_failed == 0
        assert report.details == []
        assert not report.all_passed

    def test_all_passed_true(self):
        report = DataQualityReport(checks_passed=3, checks_failed=0)
        assert report.all_passed
        assert report.total_checks == 3

    def test_all_passed_false(self):
        report = DataQualityReport(checks_passed=2, checks_failed=1)
        assert not report.all_passed

    def test_to_dict(self):
        report = DataQualityReport(
            summary="All good",
            checks_passed=2,
            checks_failed=0,
            details=[{"check": "freshness", "status": "passed"}],
        )
        d = report.to_dict()
        assert d["summary"] == "All good"
        assert d["checks_passed"] == 2
        assert d["checks_failed"] == 0
        assert d["all_passed"] is True
        assert d["total_checks"] == 2


class TestCheckFreshness:
    def test_fresh_timestamp(self, quality_engine):
        now = datetime.now(timezone.utc)
        assert quality_engine.check_freshness(now, max_age_seconds=60)

    def test_stale_timestamp(self, quality_engine):
        old = datetime.now(timezone.utc) - timedelta(seconds=120)
        assert not quality_engine.check_freshness(old, max_age_seconds=60)

    def test_naive_timestamp(self, quality_engine):
        naive = datetime.now() - timedelta(seconds=30)
        assert quality_engine.check_freshness(naive, max_age_seconds=60)


class TestCheckCompleteness:
    def test_complete_df(self, quality_engine):
        df = pd.DataFrame(
            {"close": range(100)},
            index=pd.date_range("2024-01-01", periods=100, freq="1min"),
        )
        result = quality_engine.check_completeness(df, "1min")
        assert result["is_complete"] is True
        assert result["missing_pct"] == 0.0
        assert result["gap_count"] == 0

    def test_empty_df(self, quality_engine):
        df = pd.DataFrame()
        result = quality_engine.check_completeness(df, "1min")
        assert result["is_complete"] is False

    def test_df_with_gaps(self, quality_engine):
        idx = pd.to_datetime([
            "2024-01-01 00:00", "2024-01-01 00:01",
            "2024-01-01 00:05", "2024-01-01 00:06",
        ])
        df = pd.DataFrame({"close": [1, 2, 3, 4]}, index=idx)
        result = quality_engine.check_completeness(df, "1min")
        assert result["gap_count"] >= 1
        assert not result["is_complete"]

    def test_df_with_missing_values(self, quality_engine):
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        df = pd.DataFrame({"a": [1, 2, np.nan, 4, 5, 6, 7, 8, 9, 10]}, index=idx)
        result = quality_engine.check_completeness(df, "1min")
        assert result["missing_pct"] > 0
        assert not result["is_complete"]

    def test_non_datetime_index(self, quality_engine):
        df = pd.DataFrame({"a": [1, 2, 3]})
        result = quality_engine.check_completeness(df, "1min")
        assert result["gap_count"] == 0


class TestDetectOutliers:
    def test_iqr_no_outliers(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        outliers = quality_engine.detect_outliers(series, method="iqr")
        assert len(outliers) == 0

    def test_iqr_with_outliers(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        outliers = quality_engine.detect_outliers(series, method="iqr")
        assert len(outliers) >= 1

    def test_zscore_no_outliers(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        outliers = quality_engine.detect_outliers(series, method="zscore")
        assert len(outliers) == 0

    def test_zscore_with_outliers(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        outliers = quality_engine.detect_outliers(series, method="zscore", threshold=2.0)
        assert len(outliers) >= 1

    def test_empty_series(self, quality_engine):
        assert quality_engine.detect_outliers(pd.Series([])) == []

    def test_non_numeric_series(self, quality_engine):
        series = pd.Series(["a", "b", "c"])
        assert quality_engine.detect_outliers(series) == []

    def test_too_few_values(self, quality_engine):
        series = pd.Series([1, 2, 3])
        assert quality_engine.detect_outliers(series) == []

    def test_unknown_method(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 100])
        outliers = quality_engine.detect_outliers(series, method="unknown")
        assert len(outliers) == 0

    def test_zscore_zero_std(self, quality_engine):
        series = pd.Series([5, 5, 5, 5, 5])
        outliers = quality_engine.detect_outliers(series, method="zscore")
        assert len(outliers) == 0


class TestValidateSchema:
    def test_valid_schema(self, quality_engine):
        data = {"price": 100.0, "volume": 500.0}
        schema = {"price": float, "volume": float}
        errors = quality_engine.validate_schema(data, schema)
        assert len(errors) == 0

    def test_missing_field(self, quality_engine):
        data = {"price": 100.0}
        schema = {"price": float, "volume": float}
        errors = quality_engine.validate_schema(data, schema)
        assert len(errors) == 1
        assert "Missing required field" in errors[0]

    def test_wrong_type(self, quality_engine):
        data = {"price": "not_a_float", "volume": 500.0}
        schema = {"price": float, "volume": float}
        errors = quality_engine.validate_schema(data, schema)
        assert len(errors) == 1
        assert "expected float" in errors[0]

    def test_none_value_allowed(self, quality_engine):
        data = {"price": None, "volume": 500.0}
        schema = {"price": float, "volume": float}
        errors = quality_engine.validate_schema(data, schema)
        assert len(errors) == 0  # None is allowed

    def test_int_accepted_as_float(self, quality_engine):
        data = {"price": 100, "volume": 500.0}
        schema = {"price": float, "volume": float}
        errors = quality_engine.validate_schema(data, schema)
        # int is not a float in isinstance check
        assert len(errors) == 1


class TestRunChecks:
    def test_run_freshness_check_pass(self, quality_engine):
        data = {"timestamp": datetime.now(timezone.utc)}
        config = {"freshness": {"max_age_seconds": 60}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_passed == 1
        assert report.checks_failed == 0
        assert report.all_passed

    def test_run_freshness_check_fail(self, quality_engine):
        data = {"timestamp": datetime.now(timezone.utc) - timedelta(seconds=120)}
        config = {"freshness": {"max_age_seconds": 60}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_passed == 0
        assert report.checks_failed == 1
        assert not report.all_passed

    def test_run_completeness_check(self, quality_engine):
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        df = pd.DataFrame({"close": range(10)}, index=idx)
        data = {"df": df}
        config = {"completeness": {"expected_interval": "1min"}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_passed == 1
        assert report.checks_failed == 0

    def test_run_outlier_check(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 100])
        data = {"series": series}
        config = {"outliers": {"method": "iqr"}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_failed == 1  # Has outliers

    def test_run_schema_check(self, quality_engine):
        data = {"record": {"price": 100.0, "volume": 500}}
        config = {"schema": {"schema": {"price": float, "volume": int}}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_passed == 1

    def test_run_multiple_checks(self, quality_engine):
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")
        df = pd.DataFrame({"close": range(10)}, index=idx)
        series = pd.Series([1, 2, 3, 4, 5])
        data = {
            "timestamp": datetime.now(timezone.utc),
            "df": df,
            "series": series,
        }
        config = {
            "freshness": {"max_age_seconds": 60},
            "completeness": {"expected_interval": "1min"},
            "outliers": {"method": "iqr"},
        }
        report = quality_engine.run_checks(data, config)
        assert report.total_checks == 3
        assert report.checks_passed == 3

    def test_run_no_checks(self, quality_engine):
        data = {}
        config = {}
        report = quality_engine.run_checks(data, config)
        assert report.total_checks == 0
        assert "No checks" in report.summary

    def test_run_missing_data_for_check(self, quality_engine):
        data = {}
        config = {"freshness": {"max_age_seconds": 60}}
        report = quality_engine.run_checks(data, config)
        assert report.total_checks == 0

    def test_run_check_with_outliers_pass(self, quality_engine):
        series = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        data = {"series": series}
        config = {"outliers": {"method": "iqr"}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_passed == 1
        assert report.checks_failed == 0

    def test_run_check_schema_fail(self, quality_engine):
        data = {"record": {"price": "wrong_type"}}
        config = {"schema": {"schema": {"price": float}}}
        report = quality_engine.run_checks(data, config)
        assert report.checks_failed == 1
        assert len(report.details[0]["errors"]) == 1
