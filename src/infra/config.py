"""DATS — Infrastructure Configuration Module.

Pydantic v2-based settings management with environment variable support.
All settings are singleton-accessible via ``get_config()`` using ``functools.lru_cache``.

Example:
    >>> from infra.config import get_config
    >>> cfg = get_config()
    >>> cfg.app.name
    'dats'
    >>> cfg.database.pool_size
    10
"""

from __future__ import annotations

import json
import secrets
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment enumeration."""

    LOCAL = "local"
    DEV = "development"
    STAGING = "staging"
    PROD = "production"
    TEST = "test"


class LogFormat(str, Enum):
    """Structured logging output format."""

    JSON = "json"
    CONSOLE = "console"


# ---------------------------------------------------------------------------
# Sub-configuration models
# ---------------------------------------------------------------------------


class AppConfig(BaseSettings):
    """Application identity and runtime settings.

    Environment variables (all prefixed with ``APP_``):
    * ``APP_NAME`` — application name (default: ``dats``)
    * ``APP_VERSION`` — semantic version (default: ``0.6.0``)
    * ``APP_DEBUG`` — debug mode flag (default: ``False``)
    * ``APP_ENV`` — environment name (default: ``local``)
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    name: str = Field(default="dats", description="Application name.")
    version: str = Field(default="0.6.0", description="Semantic version.")
    debug: bool = Field(default=False, description="Debug mode flag.")
    env: Environment = Field(default=Environment.LOCAL, description="Deployment environment.")


class DatabaseConfig(BaseSettings):
    """Async PostgreSQL connection settings (asyncpg driver).

    Environment variables (all prefixed with ``DB_``):
    * ``DB_HOST``, ``DB_PORT``, ``DB_USER``, ``DB_PASSWORD``, ``DB_NAME``
    * ``DB_POOL_SIZE`` (default: 10)
    * ``DB_MAX_OVERFLOW`` (default: 20)
    * ``DB_ECHO`` (default: False)
    * ``DB_POOL_RECYCLE`` (default: 3600)
    * ``DB_POOL_TIMEOUT`` (default: 30)
    * ``DB_SSL_MODE`` (default: prefer)
    """

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    user: str = Field(default="dats")
    password: str = Field(default="")
    name: str = Field(default="dats")
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    echo: bool = Field(default=False)
    pool_recycle: int = Field(default=3600, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    ssl_mode: str = Field(default="prefer")

    @property
    def asyncpg_url(self) -> str:
        """Build the asyncpg-compatible DSN."""
        auth = f"{self.user}:{self.password}" if self.password else self.user
        return (
            f"postgresql+asyncpg://{auth}"
            f"@{self.host}:{self.port}/{self.name}"
            f"?ssl={self.ssl_mode}"
        )

    @field_validator("port", "pool_size", "max_overflow", "pool_recycle", "pool_timeout", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None


class RedisConfig(BaseSettings):
    """Redis connection settings.

    Environment variables (all prefixed with ``REDIS_``):
    * ``REDIS_HOST``, ``REDIS_PORT``, ``REDIS_DB``, ``REDIS_PASSWORD``
    * ``REDIS_DECODE_RESPONSES`` (default: True)
    * ``REDIS_SOCKET_TIMEOUT`` (default: 5)
    * ``REDIS_SOCKET_CONNECT_TIMEOUT`` (default: 5)
    * ``REDIS_HEALTH_CHECK_INTERVAL`` (default: 30)
    * ``REDIS_MAX_CONNECTIONS``
    """

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0, ge=0)
    password: str | None = Field(default=None)
    decode_responses: bool = Field(default=True)
    socket_timeout: int = Field(default=5, ge=1)
    socket_connect_timeout: int = Field(default=5, ge=1)
    health_check_interval: int = Field(default=30, ge=1)
    max_connections: int | None = Field(default=None)

    @field_validator("port", "db", "socket_timeout", "socket_connect_timeout", "health_check_interval", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None


class KafkaConfig(BaseSettings):
    """Kafka (AIOKafka) producer/consumer settings.

    Environment variables (all prefixed with ``KAFKA_``):
    * ``KAFKA_BOOTSTRAP_SERVERS`` (default: localhost:9092)
    * ``KAFKA_CLIENT_ID``, ``KAFKA_GROUP_ID``
    * ``KAFKA_ACKS``, ``KAFKA_RETRIES``, ``KAFKA_RETRY_BACKOFF_MS``
    * ``KAFKA_REQUEST_TIMEOUT_MS``, ``KAFKA_AUTO_OFFSET_RESET``
    * ``KAFKA_ENABLE_AUTO_COMMIT``, ``KAFKA_MAX_POLL_RECORDS``
    * ``KAFKA_SESSION_TIMEOUT_MS``
    """

    model_config = SettingsConfigDict(
        env_prefix="KAFKA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bootstrap_servers: str = Field(default="localhost:9092")
    client_id: str = Field(default="dats")
    group_id: str = Field(default="dats-consumer-group")
    acks: str = Field(default="all")
    retries: int = Field(default=3, ge=0)
    retry_backoff_ms: int = Field(default=1000, ge=0)
    request_timeout_ms: int = Field(default=30000, ge=1000)
    auto_offset_reset: str = Field(default="earliest")
    enable_auto_commit: bool = Field(default=True)
    max_poll_records: int = Field(default=500, ge=1)
    session_timeout_ms: int = Field(default=10000, ge=1000)

    # Topic definitions
    topics: dict[str, str] = Field(
        default_factory=lambda: {
            "TRADING_SIGNALS": "dats.trading.signals",
            "PORTFOLIO_UPDATES": "dats.portfolio.updates",
            "RISK_ALERTS": "dats.risk.alerts",
            "MARKET_DATA": "dats.market.data",
        },
    )

    @field_validator("retries", "retry_backoff_ms", "request_timeout_ms", "max_poll_records", "session_timeout_ms", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None


class LoggingConfig(BaseSettings):
    """Structured logging configuration (structlog).

    Environment variables (all prefixed with ``LOG_``):
    * ``LOG_LEVEL`` (default: INFO)
    * ``LOG_FORMAT`` — ``json`` or ``console`` (default: json)
    * ``LOG_INCLUDE_TRACEBACK`` (default: True)
    * ``LOG_LOGGER_NAME`` (default: dats)
    * ``LOG_HANDLERS`` — comma-separated or JSON list (default: [console])
    """

    model_config = SettingsConfigDict(
        env_prefix="LOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    level: str = Field(default="INFO")
    format: LogFormat = Field(default=LogFormat.JSON)
    include_traceback: bool = Field(default=True)
    logger_name: str = Field(default="dats")
    handlers: list[str] = Field(default_factory=lambda: ["console"])

    @field_validator("handlers", mode="before")
    @classmethod
    def _parse_handlers(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return json.loads(stripped)
            return [h.strip() for h in stripped.split(",") if h.strip()]
        return value if value is not None else ["console"]


class MetricsConfig(BaseSettings):
    """Prometheus metrics endpoint configuration.

    Environment variables (all prefixed with ``METRICS_``):
    * ``METRICS_PORT`` (default: 9090)
    * ``METRICS_PREFIX`` (default: dats)
    * ``METRICS_PATH`` (default: /metrics)
    * ``METRICS_ENABLED`` (default: True)
    """

    model_config = SettingsConfigDict(
        env_prefix="METRICS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    port: int = Field(default=9090, ge=1024, le=65535)
    prefix: str = Field(default="dats")
    path: str = Field(default="/metrics")
    enabled: bool = Field(default=True)

    @field_validator("port", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None


class SecurityConfig(BaseSettings):
    """JWT and authentication security settings.

    Environment variables (all prefixed with ``SECURITY_``):
    * ``SECURITY_JWT_SECRET`` (auto-generated if not set)
    * ``SECURITY_TOKEN_EXPIRY_MINUTES`` (default: 60)
    * ``SECURITY_ALGORITHM`` (default: HS256)
    * ``SECURITY_REFRESH_TOKEN_EXPIRY_DAYS`` (default: 7)
    """

    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    jwt_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
    )
    token_expiry_minutes: int = Field(default=60, ge=1)
    algorithm: str = Field(default="HS256")
    refresh_token_expiry_days: int = Field(default=7, ge=1)

    @field_validator("token_expiry_minutes", "refresh_token_expiry_days", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None


class TradingConfig(BaseSettings):
    """Trading engine parameters (pilot mode).

    Environment variables (all prefixed with ``TRADING_``):
    * ``TRADING_PILOT_MIN_USD`` (default: 1.0)
    * ``TRADING_PILOT_MAX_USD`` (default: 2.0)
    * ``TRADING_SLIPPAGE_BPS`` (default: 30)
    * ``TRADING_PRICE_IMPACT_BPS`` (default: 20)
    * ``TRADING_MAX_OPEN_POSITIONS`` (default: 10)
    * ``TRADING_ENABLE_AUTO_TRADE`` (default: False)
    * ``TRADING_PAPER_TRADING`` (default: True)
    """

    model_config = SettingsConfigDict(
        env_prefix="TRADING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    pilot_min_usd: float = Field(default=1.0, ge=0.0)
    pilot_max_usd: float = Field(default=2.0, ge=0.0)
    slippage_bps: int = Field(
        default=30, ge=0, description="Slippage tolerance in basis points."
    )
    price_impact_bps: int = Field(
        default=20, ge=0, description="Max price-impact in basis points."
    )
    max_open_positions: int = Field(default=10, ge=1)
    enable_auto_trade: bool = Field(default=False)
    paper_trading: bool = Field(default=True)

    @field_validator("pilot_min_usd", "pilot_max_usd", mode="before")
    @classmethod
    def _coerce_float(cls, value: Any) -> float:
        return float(value) if value is not None else None

    @field_validator("slippage_bps", "price_impact_bps", "max_open_positions", mode="before")
    @classmethod
    def _coerce_int(cls, value: Any) -> int:
        return int(value) if value is not None else None

    @property
    def slippage_decimal(self) -> float:
        """Slippage as a decimal fraction (e.g. 30 bps → 0.0030)."""
        return self.slippage_bps / 10_000

    @property
    def price_impact_decimal(self) -> float:
        """Price impact as a decimal fraction (e.g. 20 bps → 0.0020)."""
        return self.price_impact_bps / 10_000


# ---------------------------------------------------------------------------
# Root settings aggregator
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Root configuration object — aggregates all sub-configs.

    Access individual domains via attribute notation::

        settings.app.name
        settings.database.asyncpg_url
        settings.redis.host
        settings.kafka.topics["TRADING_SIGNALS"]
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app: AppConfig = Field(default_factory=AppConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)

    @classmethod
    def from_env_file(cls, path: str | Path) -> Settings:
        """Load settings from a specific ``.env`` file path."""
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Env file not found: {resolved}")
        # Pass _env_file to nested sub-configs so they all read from the same file
        return cls(
            _env_file=resolved,
            app=AppConfig(_env_file=resolved),
            database=DatabaseConfig(_env_file=resolved),
            redis=RedisConfig(_env_file=resolved),
            kafka=KafkaConfig(_env_file=resolved),
            logging=LoggingConfig(_env_file=resolved),
            metrics=MetricsConfig(_env_file=resolved),
            security=SecurityConfig(_env_file=resolved),
            trading=TradingConfig(_env_file=resolved),
        )  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """Return the cached singleton ``Settings`` instance.

    The first call parses environment variables / ``.env`` file; subsequent
    calls return the cached object for the lifetime of the process.
    """
    return Settings()


def clear_config_cache() -> None:
    """Clear the singleton config cache — useful in tests."""
    get_config.cache_clear()
