"""Tests for production configuration loader."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from system.config_loader import ConfigError, ConfigLoader


class TestConfigLoader(unittest.TestCase):
    """Tests for configuration loading."""

    def tearDown(self):
        """Clean environment variables after each test."""
        for key in list(os.environ.keys()):
            if key.startswith("DATS_"):
                del os.environ[key]

    def test_default_values(self):
        """Defaults loaded when no env vars set."""
        loader = ConfigLoader()
        loader.load()
        self.assertEqual(loader.trading.initial_capital, 100000.0)
        self.assertEqual(loader.risk.var_confidence, 0.95)
        self.assertEqual(loader.data.redis_url, "redis://localhost:6379")
        self.assertEqual(loader.monitoring.log_level, "INFO")

    def test_env_override(self):
        """Environment variables override defaults."""
        os.environ["DATS_INITIAL_CAPITAL"] = "500000"
        os.environ["DATS_MAX_LEVERAGE"] = "3.5"
        os.environ["DATS_LOG_LEVEL"] = "DEBUG"

        loader = ConfigLoader()
        loader.load()

        self.assertEqual(loader.trading.initial_capital, 500000.0)
        self.assertEqual(loader.trading.max_leverage, 3.5)
        self.assertEqual(loader.monitoring.log_level, "DEBUG")

    def test_type_coercion(self):
        """Types coerced from strings."""
        os.environ["DATS_LOOKBACK_BARS"] = "50"
        os.environ["DATS_ENABLE_KILL_SWITCH"] = "false"
        os.environ["DATS_SLIPPAGE_BPS"] = "5.5"

        loader = ConfigLoader()
        loader.load()

        self.assertEqual(loader.trading.lookback_bars, 50)
        self.assertEqual(loader.risk.enable_kill_switch, False)
        self.assertEqual(loader.trading.slippage_bps, 5.5)

    def test_bool_coercion_variants(self):
        """Boolean values from various string formats."""
        for val, expected in [("true", True), ("1", True), ("yes", True), ("on", True),
                               ("false", False), ("0", False), ("no", False), ("off", False)]:
            os.environ["DATS_ENABLE_KILL_SWITCH"] = val
            loader = ConfigLoader()
            loader.load()
            self.assertEqual(loader.risk.enable_kill_switch, expected, f"Failed for {val}")
            del os.environ["DATS_ENABLE_KILL_SWITCH"]

    def test_invalid_type_coercion(self):
        """Invalid type raises ConfigError."""
        os.environ["DATS_INITIAL_CAPITAL"] = "not_a_number"
        loader = ConfigLoader()
        with self.assertRaises(ConfigError) as ctx:
            loader.load()
        self.assertEqual(ctx.exception.key, "INITIAL_CAPITAL")

    def test_validation_pass(self):
        """Valid config passes validation."""
        loader = ConfigLoader()
        loader.load()
        errors = loader.validate()
        self.assertEqual(len(errors), 0)

    def test_validation_fail_capital(self):
        """Zero capital fails validation."""
        os.environ["DATS_INITIAL_CAPITAL"] = "0"
        loader = ConfigLoader()
        loader.load()
        errors = loader.validate()
        self.assertTrue(any(e.key == "INITIAL_CAPITAL" for e in errors))

    def test_validation_fail_position_pct(self):
        """Invalid position pct fails validation."""
        os.environ["DATS_MAX_POSITION_PCT"] = "1.5"
        loader = ConfigLoader()
        loader.load()
        errors = loader.validate()
        self.assertTrue(any(e.key == "MAX_POSITION_PCT" for e in errors))

    def test_validation_fail_var_method(self):
        """Invalid VaR method fails validation."""
        os.environ["DATS_VAR_METHOD"] = "invalid"
        loader = ConfigLoader()
        loader.load()
        errors = loader.validate()
        self.assertTrue(any(e.key == "VAR_METHOD" for e in errors))

    def test_prefix_custom(self):
        """Custom prefix used."""
        os.environ["MYAPP_INITIAL_CAPITAL"] = "250000"
        loader = ConfigLoader(prefix="MYAPP_")
        loader.load()
        self.assertEqual(loader.trading.initial_capital, 250000.0)
        del os.environ["MYAPP_INITIAL_CAPITAL"]

    def test_to_dict(self):
        """Config exports to dict."""
        loader = ConfigLoader()
        loader.load()
        d = loader.to_dict()
        self.assertIn("trading", d)
        self.assertIn("risk", d)
        self.assertIn("data", d)
        self.assertIn("monitoring", d)
        self.assertEqual(d["trading"]["initial_capital"], 100000.0)

    def test_immutability(self):
        """Config objects are frozen."""
        loader = ConfigLoader()
        loader.load()
        with self.assertRaises(Exception):
            loader.trading.initial_capital = 999


if __name__ == "__main__":
    unittest.main(verbosity=2)
