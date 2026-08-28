"""Production configuration loader with environment variable support.

Provides strict config validation, type coercion, and secrets
resolution for production deployments.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""

    def __init__(self, key: str, reason: str):
        self.key = key
        self.reason = reason
        super().__init__(f"Config error for '{key}': {reason}")


@dataclass(frozen=True)
class TradingConfig:
    """Trading system configuration."""

    initial_capital: float = 100000.0
    max_position_pct: float = 0.20
    max_leverage: float = 2.0
    max_drawdown_pct: float = 0.10
    commission_per_trade: float = 1.0
    slippage_bps: float = 2.0
    default_strategy: str = "momentum"
    lookback_bars: int = 20


@dataclass(frozen=True)
class RiskConfig:
    """Risk management configuration."""

    var_confidence: float = 0.95
    var_method: str = "historical"
    daily_loss_limit_pct: float = 0.05
    consecutive_losses_limit: int = 5
    kill_switch_cooldown_seconds: int = 300
    enable_kill_switch: bool = True


@dataclass(frozen=True)
class DataConfig:
    """Data source configuration."""

    redis_url: str = "redis://localhost:6379"
    kafka_brokers: str = "localhost:9092"
    backfill_days: int = 365
    stale_price_seconds: int = 60


@dataclass(frozen=True)
class MonitoringConfig:
    """Monitoring and alerting configuration."""

    metrics_retention_points: int = 10000
    alert_cooldown_seconds: float = 300.0
    health_check_timeout: float = 5.0
    log_level: str = "INFO"


class ConfigLoader:
    """Loads and validates production configuration from environment.

    Supports typed coercion, defaults, and strict validation.
    """

    def __init__(self, prefix: str = "DATS_"):
        """Initialize config loader.

        Args:
            prefix: Environment variable prefix.
        """
        self.prefix = prefix
        self._trading = TradingConfig()
        self._risk = RiskConfig()
        self._data = DataConfig()
        self._monitoring = MonitoringConfig()

    def load(self) -> "ConfigLoader":
        """Load all configuration from environment variables.

        Returns:
            Self for chaining.
        """
        self._trading = self._load_trading()
        self._risk = self._load_risk()
        self._data = self._load_data()
        self._monitoring = self._load_monitoring()
        return self

    def _get_env(self, key: str, default: Any, type_fn: type = str) -> Any:
        """Get environment variable with type coercion."""
        value = os.environ.get(f"{self.prefix}{key}")
        if value is None:
            return default
        if type_fn == bool:
            return value.lower() in ("true", "1", "yes", "on")
        try:
            return type_fn(value)
        except (ValueError, TypeError):
            raise ConfigError(key, f"Cannot coerce '{value}' to {type_fn.__name__}")

    def _load_trading(self) -> TradingConfig:
        return TradingConfig(
            initial_capital=self._get_env("INITIAL_CAPITAL", 100000.0, float),
            max_position_pct=self._get_env("MAX_POSITION_PCT", 0.20, float),
            max_leverage=self._get_env("MAX_LEVERAGE", 2.0, float),
            max_drawdown_pct=self._get_env("MAX_DRAWDOWN_PCT", 0.10, float),
            commission_per_trade=self._get_env("COMMISSION", 1.0, float),
            slippage_bps=self._get_env("SLIPPAGE_BPS", 2.0, float),
            default_strategy=self._get_env("DEFAULT_STRATEGY", "momentum"),
            lookback_bars=self._get_env("LOOKBACK_BARS", 20, int),
        )

    def _load_risk(self) -> RiskConfig:
        return RiskConfig(
            var_confidence=self._get_env("VAR_CONFIDENCE", 0.95, float),
            var_method=self._get_env("VAR_METHOD", "historical"),
            daily_loss_limit_pct=self._get_env("DAILY_LOSS_LIMIT_PCT", 0.05, float),
            consecutive_losses_limit=self._get_env("CONSECUTIVE_LOSSES", 5, int),
            kill_switch_cooldown_seconds=self._get_env("KILL_SWITCH_COOLDOWN", 300, int),
            enable_kill_switch=self._get_env("ENABLE_KILL_SWITCH", True, bool),
        )

    def _load_data(self) -> DataConfig:
        return DataConfig(
            redis_url=self._get_env("REDIS_URL", "redis://localhost:6379"),
            kafka_brokers=self._get_env("KAFKA_BROKERS", "localhost:9092"),
            backfill_days=self._get_env("BACKFILL_DAYS", 365, int),
            stale_price_seconds=self._get_env("STALE_PRICE_SECONDS", 60, int),
        )

    def _load_monitoring(self) -> MonitoringConfig:
        return MonitoringConfig(
            metrics_retention_points=self._get_env("METRICS_RETENTION", 10000, int),
            alert_cooldown_seconds=self._get_env("ALERT_COOLDOWN", 300.0, float),
            health_check_timeout=self._get_env("HEALTH_TIMEOUT", 5.0, float),
            log_level=self._get_env("LOG_LEVEL", "INFO"),
        )

    @property
    def trading(self) -> TradingConfig:
        return self._trading

    @property
    def risk(self) -> RiskConfig:
        return self._risk

    @property
    def data(self) -> DataConfig:
        return self._data

    @property
    def monitoring(self) -> MonitoringConfig:
        return self._monitoring

    def validate(self) -> list[ConfigError]:
        """Validate loaded configuration.

        Returns:
            List of validation errors (empty if valid).
        """
        errors: list[ConfigError] = []

        # Trading validation
        if self._trading.initial_capital <= 0:
            errors.append(ConfigError("INITIAL_CAPITAL", "Must be positive"))
        if not 0 < self._trading.max_position_pct <= 1:
            errors.append(ConfigError("MAX_POSITION_PCT", "Must be in (0, 1]"))
        if self._trading.max_leverage < 1:
            errors.append(ConfigError("MAX_LEVERAGE", "Must be >= 1"))

        # Risk validation
        if not 0 < self._risk.var_confidence < 1:
            errors.append(ConfigError("VAR_CONFIDENCE", "Must be in (0, 1)"))
        if self._risk.var_method not in ("historical", "parametric", "monte_carlo"):
            errors.append(ConfigError("VAR_METHOD", "Must be historical, parametric, or monte_carlo"))

        # Data validation
        if self._data.stale_price_seconds < 1:
            errors.append(ConfigError("STALE_PRICE_SECONDS", "Must be >= 1"))

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Export all config as dictionary."""
        return {
            "trading": self._trading.__dict__,
            "risk": self._risk.__dict__,
            "data": self._data.__dict__,
            "monitoring": self._monitoring.__dict__,
        }
