"""Tests for ``src.infra.config`` — Pydantic v2 Settings Module.

Covers:
* Default value validation
* Environment variable loading
* Alias resolution
* Custom validators (coercion)
* Singleton behaviour via ``lru_cache``
* Trading decimal properties
* ``from_env_file`` loading
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.infra.config import (
    AppConfig,
    DatabaseConfig,
    Environment,
    KafkaConfig,
    LogFormat,
    LoggingConfig,
    MetricsConfig,
    RedisConfig,
    SecurityConfig,
    Settings,
    TradingConfig,
    clear_config_cache,
    get_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_config_cache() -> Generator[None, None, None]:
    """Ensure every test starts with a fresh singleton cache."""
    clear_config_cache()
    yield
    clear_config_cache()


@pytest.fixture
def env_vars() -> Generator[dict[str, str], None, None]:
    """Provide a mutable reference to ``os.environ`` for a single test.

    The global ``env_isolation`` fixture (in ``tests/conftest.py``) already
    handles snapshot / restore, so this fixture only needs to yield the
    live dict.
    """
    yield os.environ


# ===========================================================================
# AppConfig
# ===========================================================================


class TestAppConfig:
    """Unit tests for ``AppConfig``."""

    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.name == "dats"
        assert cfg.version == "0.6.0"
        assert cfg.debug is False
        assert cfg.env == Environment.LOCAL

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["APP_NAME"] = "test-app"
        env_vars["APP_VERSION"] = "1.2.3"
        env_vars["APP_DEBUG"] = "true"
        env_vars["APP_ENV"] = "test"

        cfg = AppConfig()
        assert cfg.name == "test-app"
        assert cfg.version == "1.2.3"
        assert cfg.debug is True
        assert cfg.env == Environment.TEST

    def test_env_enum_variants(self) -> None:
        assert Environment.LOCAL == "local"
        assert Environment.DEV == "development"
        assert Environment.STAGING == "staging"
        assert Environment.PROD == "production"
        assert Environment.TEST == "test"


# ===========================================================================
# DatabaseConfig
# ===========================================================================


class TestDatabaseConfig:
    """Unit tests for ``DatabaseConfig``."""

    def test_defaults(self) -> None:
        cfg = DatabaseConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 5432
        assert cfg.user == "dats"
        assert cfg.password == "dats"
        assert cfg.name == "dats"
        assert cfg.pool_size == 10
        assert cfg.max_overflow == 20
        assert cfg.echo is False
        assert cfg.pool_recycle == 3600
        assert cfg.pool_timeout == 30
        assert cfg.ssl_mode == "prefer"

    def test_asyncpg_url(self) -> None:
        cfg = DatabaseConfig(
            host="db.example.com",
            port=5433,
            user="admin",
            password="secret123",
            name="trading",
            ssl_mode="require",
        )
        expected = "postgresql+asyncpg://admin:secret123@db.example.com:5433/trading?ssl=require"
        assert cfg.asyncpg_url == expected

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["DB_HOST"] = "postgres.internal"
        env_vars["DB_PORT"] = "5433"
        env_vars["DB_POOL_SIZE"] = "25"
        env_vars["DB_ECHO"] = "1"

        cfg = DatabaseConfig()
        assert cfg.host == "postgres.internal"
        assert cfg.port == 5433
        assert cfg.pool_size == 25
        assert cfg.echo is True

    def test_pool_size_validation(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseConfig(pool_size=0)

    def test_int_coercion_from_string(self, env_vars: dict[str, str]) -> None:
        """Ensure string env vars are coerced to int."""
        env_vars["DB_POOL_SIZE"] = "42"
        env_vars["DB_MAX_OVERFLOW"] = "99"
        cfg = DatabaseConfig()
        assert cfg.pool_size == 42
        assert cfg.max_overflow == 99


# ===========================================================================
# RedisConfig
# ===========================================================================


class TestRedisConfig:
    """Unit tests for ``RedisConfig``."""

    def test_defaults(self) -> None:
        cfg = RedisConfig()
        assert cfg.host == "localhost"
        assert cfg.port == 6379
        assert cfg.db == 0
        assert cfg.password is None
        assert cfg.decode_responses is True
        assert cfg.socket_timeout == 5
        assert cfg.socket_connect_timeout == 5
        assert cfg.health_check_interval == 30
        assert cfg.max_connections is None

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["REDIS_HOST"] = "redis.internal"
        env_vars["REDIS_PORT"] = "6380"
        env_vars["REDIS_DB"] = "3"
        env_vars["REDIS_PASSWORD"] = "redis-secret"

        cfg = RedisConfig()
        assert cfg.host == "redis.internal"
        assert cfg.port == 6380
        assert cfg.db == 3
        assert cfg.password == "redis-secret"

    def test_int_coercion(self, env_vars: dict[str, str]) -> None:
        env_vars["REDIS_PORT"] = "7000"
        env_vars["REDIS_DB"] = "7"
        env_vars["REDIS_SOCKET_TIMEOUT"] = "10"
        cfg = RedisConfig()
        assert cfg.port == 7000
        assert cfg.db == 7
        assert cfg.socket_timeout == 10


# ===========================================================================
# KafkaConfig
# ===========================================================================


class TestKafkaConfig:
    """Unit tests for ``KafkaConfig``."""

    def test_defaults(self) -> None:
        cfg = KafkaConfig()
        assert cfg.bootstrap_servers == "localhost:9092"
        assert cfg.client_id == "dats"
        assert cfg.group_id == "dats-consumer-group"
        assert cfg.acks == "all"
        assert cfg.retries == 3
        assert cfg.retry_backoff_ms == 1000
        assert cfg.request_timeout_ms == 30000
        assert cfg.auto_offset_reset == "earliest"
        assert cfg.enable_auto_commit is True
        assert cfg.max_poll_records == 500
        assert cfg.session_timeout_ms == 10000

    def test_topics(self) -> None:
        cfg = KafkaConfig()
        assert cfg.topics["TRADING_SIGNALS"] == "dats.trading.signals"
        assert cfg.topics["PORTFOLIO_UPDATES"] == "dats.portfolio.updates"
        assert cfg.topics["RISK_ALERTS"] == "dats.risk.alerts"
        assert cfg.topics["MARKET_DATA"] == "dats.market.data"

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["KAFKA_BOOTSTRAP_SERVERS"] = "kafka1:9092,kafka2:9092"
        env_vars["KAFKA_CLIENT_ID"] = "dats-staging"
        env_vars["KAFKA_RETRIES"] = "5"

        cfg = KafkaConfig()
        assert cfg.bootstrap_servers == "kafka1:9092,kafka2:9092"
        assert cfg.client_id == "dats-staging"
        assert cfg.retries == 5


# ===========================================================================
# LoggingConfig
# ===========================================================================


class TestLoggingConfig:
    """Unit tests for ``LoggingConfig``."""

    def test_defaults(self) -> None:
        cfg = LoggingConfig()
        assert cfg.level == "INFO"
        assert cfg.format == LogFormat.JSON
        assert cfg.include_traceback is True
        assert cfg.logger_name == "dats"
        assert cfg.handlers == ["console"]

    def test_handlers_parsing(self, env_vars: dict[str, str]) -> None:
        # pydantic-settings v2 auto-decodes list[str] from env as JSON,
        # so we must use a JSON array string.  The _parse_handlers validator
        # also supports comma-separated strings for direct kwargs.
        env_vars["LOG_HANDLERS"] = '["console", "file", "syslog"]'
        cfg = LoggingConfig()
        assert cfg.handlers == ["console", "file", "syslog"]

    def test_handlers_parsing_comma_direct(self) -> None:
        # When passing a plain string directly (not via env), the validator
        # handles comma-separated format.
        cfg = LoggingConfig(handlers="console,file,syslog")
        assert cfg.handlers == ["console", "file", "syslog"]

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["LOG_LEVEL"] = "DEBUG"
        env_vars["LOG_FORMAT"] = "console"
        cfg = LoggingConfig()
        assert cfg.level == "DEBUG"
        assert cfg.format == LogFormat.CONSOLE


# ===========================================================================
# MetricsConfig
# ===========================================================================


class TestMetricsConfig:
    """Unit tests for ``MetricsConfig``."""

    def test_defaults(self) -> None:
        cfg = MetricsConfig()
        assert cfg.port == 9090
        assert cfg.prefix == "dats"
        assert cfg.path == "/metrics"
        assert cfg.enabled is True

    def test_port_validation(self) -> None:
        with pytest.raises(ValidationError):
            MetricsConfig(port=80)  # below 1024
        with pytest.raises(ValidationError):
            MetricsConfig(port=70000)  # above 65535

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["METRICS_PORT"] = "9091"
        env_vars["METRICS_PREFIX"] = "dats-staging"
        env_vars["METRICS_ENABLED"] = "false"

        cfg = MetricsConfig()
        assert cfg.port == 9091
        assert cfg.prefix == "dats-staging"
        assert cfg.enabled is False


# ===========================================================================
# SecurityConfig
# ===========================================================================


class TestSecurityConfig:
    """Unit tests for ``SecurityConfig``."""

    def test_defaults(self) -> None:
        cfg = SecurityConfig()
        assert cfg.jwt_secret is not None
        assert len(cfg.jwt_secret) >= 32
        assert cfg.token_expiry_minutes == 60
        assert cfg.algorithm == "HS256"
        assert cfg.refresh_token_expiry_days == 7

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["SECURITY_JWT_SECRET"] = "my-super-secret-key-32-bytes-long!!"
        env_vars["SECURITY_TOKEN_EXPIRY_MINUTES"] = "120"
        env_vars["SECURITY_ALGORITHM"] = "HS512"

        cfg = SecurityConfig()
        assert cfg.jwt_secret == "my-super-secret-key-32-bytes-long!!"
        assert cfg.token_expiry_minutes == 120
        assert cfg.algorithm == "HS512"


# ===========================================================================
# TradingConfig
# ===========================================================================


class TestTradingConfig:
    """Unit tests for ``TradingConfig``."""

    def test_defaults(self) -> None:
        cfg = TradingConfig()
        assert cfg.pilot_min_usd == 1.0
        assert cfg.pilot_max_usd == 2.0
        assert cfg.slippage_bps == 30
        assert cfg.price_impact_bps == 20
        assert cfg.max_open_positions == 10
        assert cfg.enable_auto_trade is False
        assert cfg.paper_trading is True

    def test_decimal_conversions(self) -> None:
        cfg = TradingConfig()
        assert cfg.slippage_decimal == 0.0030
        assert cfg.price_impact_decimal == 0.0020

    def test_from_env(self, env_vars: dict[str, str]) -> None:
        env_vars["TRADING_PILOT_MIN_USD"] = "5.0"
        env_vars["TRADING_PILOT_MAX_USD"] = "10.0"
        env_vars["TRADING_SLIPPAGE_BPS"] = "50"
        env_vars["TRADING_ENABLE_AUTO_TRADE"] = "true"

        cfg = TradingConfig()
        assert cfg.pilot_min_usd == 5.0
        assert cfg.pilot_max_usd == 10.0
        assert cfg.slippage_bps == 50
        assert cfg.enable_auto_trade is True

    def test_coercion(self, env_vars: dict[str, str]) -> None:
        env_vars["TRADING_PILOT_MIN_USD"] = "3.5"
        env_vars["TRADING_SLIPPAGE_BPS"] = "45"
        cfg = TradingConfig()
        assert cfg.pilot_min_usd == 3.5
        assert cfg.slippage_bps == 45


# ===========================================================================
# Settings (root aggregator)
# ===========================================================================


class TestSettings:
    """Unit tests for the root ``Settings`` aggregator."""

    def test_default_subconfigs(self) -> None:
        settings = Settings()
        assert isinstance(settings.app, AppConfig)
        assert isinstance(settings.database, DatabaseConfig)
        assert isinstance(settings.redis, RedisConfig)
        assert isinstance(settings.kafka, KafkaConfig)
        assert isinstance(settings.logging, LoggingConfig)
        assert isinstance(settings.metrics, MetricsConfig)
        assert isinstance(settings.security, SecurityConfig)
        assert isinstance(settings.trading, TradingConfig)

    def test_database_url_access(self) -> None:
        settings = Settings()
        url = settings.database.asyncpg_url
        assert url.startswith("postgresql+asyncpg://")
        assert "dats@localhost:5432/dats" in url

    def test_kafka_topics_access(self) -> None:
        settings = Settings()
        assert settings.kafka.topics["TRADING_SIGNALS"] == "dats.trading.signals"

    def test_trading_decimal_access(self) -> None:
        settings = Settings()
        assert settings.trading.slippage_decimal == 0.0030
        assert settings.trading.price_impact_decimal == 0.0020

    def test_from_env_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "test.env"
        env_file.write_text(
            "APP_NAME=from-file\nDB_HOST=file-db\nREDIS_HOST=file-redis\n"
        )
        settings = Settings.from_env_file(env_file)
        assert settings.app.name == "from-file"
        assert settings.database.host == "file-db"
        assert settings.redis.host == "file-redis"

    def test_from_env_file_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            Settings.from_env_file(tmp_path / "nonexistent.env")


# ===========================================================================
# Singleton (lru_cache)
# ===========================================================================


class TestSingleton:
    """Tests for the ``get_config`` singleton factory."""

    def test_singleton_identity(self) -> None:
        a = get_config()
        b = get_config()
        assert a is b

    def test_singleton_caching(self) -> None:
        cfg1 = get_config()
        cfg2 = get_config()
        assert id(cfg1) == id(cfg2)

    def test_clear_cache(self) -> None:
        cfg1 = get_config()
        clear_config_cache()
        cfg2 = get_config()
        assert cfg1 is not cfg2
        # But the new one is also cached
        cfg3 = get_config()
        assert cfg2 is cfg3

    def test_values_after_clear(self, env_vars: dict[str, str]) -> None:
        cfg1 = get_config()
        assert cfg1.app.name == "dats"

        env_vars["APP_NAME"] = "new-name"
        clear_config_cache()
        cfg2 = get_config()
        assert cfg2.app.name == "new-name"
