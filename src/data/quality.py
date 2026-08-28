"""DATS — Data Quality Engine.

Provides data-quality checks (freshness, completeness, outlier detection,
schema validation) and a reporting structure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DataQualityReport
# ---------------------------------------------------------------------------


@dataclass
class DataQualityReport:
    """Aggregated result of a data-quality check run.

    Attributes:
        summary: Human-readable summary string.
        checks_passed: Number of checks that passed.
        checks_failed: Number of checks that failed.
        details: Per-check detail records.
    """

    summary: str = ""
    checks_passed: int = 0
    checks_failed: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """Return ``True`` if all checks passed."""
        return self.checks_failed == 0 and self.checks_passed > 0

    @property
    def total_checks(self) -> int:
        """Return total number of checks run."""
        return self.checks_passed + self.checks_failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "total_checks": self.total_checks,
            "all_passed": self.all_passed,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# DataQualityEngine
# ---------------------------------------------------------------------------


class DataQualityEngine:
    """Engine for running data-quality checks on market data.

    Usage::

        engine = DataQualityEngine()
        report = engine.run_checks(data, config)
        if not report.all_passed:
            logger.warning("Data quality issues detected: %s", report.summary)
    """

    # -- Individual checks ---------------------------------------------------

    @staticmethod
    def check_freshness(timestamp: datetime, max_age_seconds: float) -> bool:
        """Check whether *timestamp* is within *max_age_seconds* of now.

        Args:
            timestamp: The timestamp to check.
            max_age_seconds: Maximum acceptable age in seconds.

        Returns:
            ``True`` if the timestamp is fresh enough.
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_seconds = (now - timestamp).total_seconds()
        return age_seconds <= max_age_seconds

    @staticmethod
    def check_completeness(df: pd.DataFrame, expected_interval: str) -> dict[str, Any]:
        """Check DataFrame completeness (missing values, gaps).

        Args:
            df: DataFrame with a DatetimeIndex.
            expected_interval: Expected frequency string, e.g. ``"1min"``.

        Returns:
            Dict with ``missing_pct``, ``gap_count``, ``is_complete``, etc.
        """
        if df.empty:
            return {
                "missing_pct": 100.0,
                "gap_count": 0,
                "is_complete": False,
                "expected_rows": 0,
                "actual_rows": 0,
            }

        missing_pct = float(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100)

        # Check temporal gaps
        if isinstance(df.index, pd.DatetimeIndex):
            expected_freq = pd.Timedelta(expected_interval)
            actual_freq = pd.Series(df.index).diff().median()
            gap_count = int(
                pd.Series(df.index).diff().dropna().gt(expected_freq * 1.5).sum()
            )
        else:
            gap_count = 0
            actual_freq = None

        is_complete = missing_pct < 1.0 and gap_count == 0

        return {
            "missing_pct": round(missing_pct, 2),
            "gap_count": gap_count,
            "is_complete": is_complete,
            "expected_rows": len(df),
            "actual_rows": len(df.dropna()),
            "median_interval": str(actual_freq) if actual_freq is not None else None,
        }

    @staticmethod
    def detect_outliers(
        series: pd.Series,
        method: str = "iqr",
        threshold: float = 3.0,
    ) -> list[int]:
        """Detect outlier indices in a numeric series.

        Args:
            series: Numeric pandas Series.
            method: ``"iqr"`` or ``"zscore"``.
            threshold: Z-score threshold (only for ``"zscore"``).

        Returns:
            List of integer index positions of outliers.
        """
        if series.empty or not np.issubdtype(series.dtype, np.number):
            return []

        clean = series.dropna()
        if len(clean) < 4:
            return []

        outlier_indices: list[int] = []

        if method == "iqr":
            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            mask = (clean < lower) | (clean > upper)
            outlier_indices = clean.index[mask].tolist()
        elif method == "zscore":
            mean = clean.mean()
            std = clean.std()
            if std == 0:
                return []
            z_scores = (clean - mean).abs() / std
            mask = z_scores > threshold
            outlier_indices = clean.index[mask].tolist()
        else:
            logger.warning("Unknown outlier detection method: %s", method)

        return outlier_indices

    @staticmethod
    def validate_schema(data: dict[str, Any], schema: dict[str, type]) -> list[str]:
        """Validate a dict against an expected schema.

        Args:
            data: Data dictionary.
            schema: Mapping of field name → expected Python type.

        Returns:
            List of error messages (empty if valid).
        """
        errors: list[str] = []
        for field_name, expected_type in schema.items():
            if field_name not in data:
                errors.append(f"Missing required field: {field_name!r}")
                continue
            value = data[field_name]
            if value is not None and not isinstance(value, expected_type):
                errors.append(
                    f"Field {field_name!r}: expected {expected_type.__name__}, "
                    f"got {type(value).__name__}"
                )
        return errors

    # -- Orchestration -------------------------------------------------------

    def run_checks(
        self,
        data: dict[str, Any],
        config: dict[str, Any],
    ) -> DataQualityReport:
        """Run a suite of data-quality checks.

        Args:
            data: Dict containing the data to check. Expected keys::

                    {
                        "timestamp": datetime,          # for freshness
                        "df": pd.DataFrame,              # for completeness
                        "series": pd.Series,             # for outlier detection
                        "record": dict,                  # for schema validation
                    }

                Not all keys are required — only checks whose required keys
                are present will run.
            config: Dict of check configurations::

                    {
                        "freshness": {"max_age_seconds": 60},
                        "completeness": {"expected_interval": "1min"},
                        "outliers": {"method": "iqr", "threshold": 3.0},
                        "schema": {"schema": {"field_name": float, ...}},
                    }

        Returns:
            ``DataQualityReport`` with aggregated results.
        """
        report = DataQualityReport()
        check_details: list[dict[str, Any]] = []
        passed = 0
        failed = 0

        # Freshness check
        if "freshness" in config and "timestamp" in data:
            cfg = config["freshness"]
            ts = data["timestamp"]
            max_age = cfg.get("max_age_seconds", 60)
            is_fresh = self.check_freshness(ts, max_age)
            detail = {
                "check": "freshness",
                "status": "passed" if is_fresh else "failed",
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "max_age_seconds": max_age,
            }
            check_details.append(detail)
            if is_fresh:
                passed += 1
            else:
                failed += 1

        # Completeness check
        if "completeness" in config and "df" in data:
            cfg = config["completeness"]
            df = data["df"]
            interval = cfg.get("expected_interval", "1min")
            result = self.check_completeness(df, interval)
            is_ok = result["is_complete"]
            detail = {
                "check": "completeness",
                "status": "passed" if is_ok else "failed",
                **result,
            }
            check_details.append(detail)
            if is_ok:
                passed += 1
            else:
                failed += 1

        # Outlier detection
        if "outliers" in config and "series" in data:
            cfg = config["outliers"]
            series = data["series"]
            method = cfg.get("method", "iqr")
            threshold = cfg.get("threshold", 3.0)
            outlier_idx = self.detect_outliers(series, method=method, threshold=threshold)
            is_ok = len(outlier_idx) == 0
            detail = {
                "check": "outliers",
                "status": "passed" if is_ok else "failed",
                "outlier_count": len(outlier_idx),
                "method": method,
                "outlier_indices": outlier_idx[:100],  # cap for report size
            }
            check_details.append(detail)
            if is_ok:
                passed += 1
            else:
                failed += 1

        # Schema validation
        if "schema" in config and "record" in data:
            cfg = config["schema"]
            record = data["record"]
            schema = cfg.get("schema", {})
            errors = self.validate_schema(record, schema)
            is_ok = len(errors) == 0
            detail = {
                "check": "schema",
                "status": "passed" if is_ok else "failed",
                "errors": errors,
            }
            check_details.append(detail)
            if is_ok:
                passed += 1
            else:
                failed += 1

        report.checks_passed = passed
        report.checks_failed = failed
        report.details = check_details

        if passed + failed == 0:
            report.summary = "No checks were run (missing data/config)."
        elif failed == 0:
            report.summary = f"All {passed} check(s) passed."
        else:
            report.summary = f"{passed} check(s) passed, {failed} check(s) failed."

        return report
