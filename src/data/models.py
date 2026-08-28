"""DATS — SQLAlchemy Data Models.

Defines the ORM models for the feature store (TimescaleDB hypertable)
and data-quality logging.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Integer,
    MetaData,
    String,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# Naming convention for Alembic / migrations
# ---------------------------------------------------------------------------

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata_obj = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Shared declarative base with naming convention."""

    metadata = metadata_obj


# ---------------------------------------------------------------------------
# FeatureRecord — TimescaleDB hypertable
# ---------------------------------------------------------------------------


class FeatureRecord(Base):
    """A single feature value stored in TimescaleDB (hypertable).

    The table should be converted to a hypertable via::

        SELECT create_hypertable('feature_records', 'timestamp');

    Attributes:
        id: UUID primary key.
        symbol: Trading symbol.
        timestamp: Feature timestamp (hypertable partitioning column).
        feature_name: Feature identifier, e.g. ``"rsi_14"``.
        feature_value: JSONB value (supports scalars, arrays, dicts).
    """

    __tablename__ = "feature_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    feature_name: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_value: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<FeatureRecord(symbol={self.symbol!r}, "
            f"feature={self.feature_name!r}, timestamp={self.timestamp!r})>"
        )


# ---------------------------------------------------------------------------
# DataQualityLog
# ---------------------------------------------------------------------------


class DataQualityLog(Base):
    """Log entry for a data-quality check result.

    Attributes:
        id: Auto-increment primary key.
        timestamp: When the check ran.
        source: Data source name (e.g. ``"jupiter"``).
        check_type: Check identifier (e.g. ``"freshness"``).
        status: ``"passed"`` or ``"failed"``.
        details: Arbitrary JSON metadata about the check.
    """

    __tablename__ = "data_quality_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # passed / failed
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DataQualityLog(source={self.source!r}, "
            f"check={self.check_type!r}, status={self.status!r})>"
        )
