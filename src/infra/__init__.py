"""DATS — Infrastructure Layer.

Exports the four foundational infrastructure modules:
* :mod:`config`     — Pydantic v2 settings with env-var support
* :mod:`database`   — Async SQLAlchemy engine + session manager
* :mod:`redis_client` — Async Redis client with JSON support
* :mod:`kafka_client` — Async Kafka producer / consumer
"""

from infra.config import (
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
from infra.database import DatabaseManager
from infra.kafka_client import (
    ALL_TOPICS,
    MARKET_DATA,
    PORTFOLIO_UPDATES,
    RISK_ALERTS,
    TRADING_SIGNALS,
    KafkaConsumer,
    KafkaMessage,
    KafkaProducer,
)
from infra.redis_client import RedisManager

__all__ = [
    # Config
    "get_config",
    "clear_config_cache",
    "Settings",
    "AppConfig",
    "DatabaseConfig",
    "RedisConfig",
    "KafkaConfig",
    "LoggingConfig",
    "LogFormat",
    "MetricsConfig",
    "SecurityConfig",
    "TradingConfig",
    "Environment",
    # Database
    "DatabaseManager",
    # Redis
    "RedisManager",
    # Kafka
    "KafkaProducer",
    "KafkaConsumer",
    "KafkaMessage",
    "TRADING_SIGNALS",
    "PORTFOLIO_UPDATES",
    "RISK_ALERTS",
    "MARKET_DATA",
    "ALL_TOPICS",
]
