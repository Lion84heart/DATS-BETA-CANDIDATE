"""DATS — Feature Store, Feature Engineering, Data Quality.

Provides the data platform layer:
* SQLAlchemy models for TimescaleDB
* Online (Redis) and offline (TimescaleDB) feature store
* Technical indicator computation
* Data quality checks and reporting
* Kafka streaming integration
"""

from data.feature_store import FeatureStore
from data.features import FeatureEngine
from data.quality import DataQualityEngine, DataQualityReport
from data.streaming import DataStreamPipeline

__all__ = [
    "FeatureStore",
    "FeatureEngine",
    "DataQualityEngine",
    "DataQualityReport",
    "DataStreamPipeline",
]
