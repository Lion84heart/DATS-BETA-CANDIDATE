"""DATS — Abstract Base Strategy.

Defines the interface that all trading strategies must implement.
Supports hot-swap parameter updates, state persistence, and health checks.
"""

from __future__ import annotations

import logging
import pickle
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from trading.schemas import (
    SignalDirection,
    StrategyConfig,
    StrategySignal,
    StrategyState,
    StrategyType,
)

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """Abstract base for all trading strategies.

    All strategies must be pickle-serializable for hot-swap deployment.
    Parameter updates are validated against bounds and clamped.
    Feature handling is NaN-safe: missing features are handled gracefully.
    """

    name: str = "base_strategy"
    strategy_type: StrategyType = StrategyType.TREND_FOLLOWING

    def __init__(self, config: StrategyConfig | None = None) -> None:
        self.config: StrategyConfig = config or StrategyConfig(
            strategy_type=self.strategy_type,
            symbol="UNKNOWN",
        )
        self.parameters: dict[str, float] = dict(self.config.parameters)
        self._apply_defaults()
        self._enabled: bool = self.config.enabled
        self._initialized: bool = False
        self._state_data: dict[str, Any] = {}
        self._last_signal_time: datetime | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Setup: load config, validate parameters, prepare state."""
        logger.info("Initializing strategy %s", self.name)
        self._validate_parameters(self.parameters)
        self._initialized = True

    async def teardown(self) -> None:
        """Cleanup: release resources, save state."""
        logger.info("Tearing down strategy %s", self.name)
        self._initialized = False

    # ------------------------------------------------------------------
    # Core — MUST OVERRIDE
    # ------------------------------------------------------------------

    @abstractmethod
    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        """Generate a trading signal from OHLCV data and pre-computed features.

        Args:
            ohlcv_df: DataFrame with OHLCV data up to the current bar.
            features: Dict of feature name -> value (may contain None values).

        Returns:
            A StrategySignal or None if no signal should be generated.
        """
        ...

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def update_parameters(self, params: dict[str, float]) -> None:
        """Hot-swap parameters without restart. Values are clamped to bounds.

        Args:
            params: Dictionary of parameter name -> new value.

        Raises:
            ValueError: If a parameter is not recognized.
        """
        bounds = self.parameter_bounds()
        for key, value in params.items():
            if key not in bounds:
                raise ValueError(
                    f"Unknown parameter '{key}' for strategy '{self.name}'. "
                    f"Known: {list(bounds.keys())}"
                )
            min_val, max_val = bounds[key]
            clamped = max(min_val, min(max_val, float(value)))
            self.parameters[key] = clamped
            logger.debug(
                "Parameter %s updated: %s -> %s (clamped to [%s, %s])",
                key, value, clamped, min_val, max_val,
            )
        # Sync back to config
        self.config.parameters = dict(self.parameters)

    def get_parameters(self) -> dict[str, float]:
        """Return current parameter values."""
        return dict(self.parameters)

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        """Return (min, max) bounds for each tunable parameter.

        Override in subclasses to define parameter search spaces.
        """
        return {}

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Return health status of the strategy."""
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "initialized": self._initialized,
            "enabled": self._enabled,
            "parameters": self.get_parameters(),
            "last_signal_time": self._last_signal_time.isoformat()
            if self._last_signal_time
            else None,
            "state_data_keys": list(self._state_data.keys()),
        }

    def get_state(self) -> dict[str, Any]:
        """Return serializable state for persistence.

        Must include all data needed to restore the strategy's internal state.
        """
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "parameters": self.get_parameters(),
            "enabled": self._enabled,
            "state_data": self._state_data,
            "last_signal_time": self._last_signal_time.isoformat()
            if self._last_signal_time
            else None,
        }

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore from serialized state.

        Args:
            state: Dictionary previously returned by get_state().
        """
        if "parameters" in state:
            self.parameters = dict(state["parameters"])
            self.config.parameters = dict(state["parameters"])
        if "enabled" in state:
            self._enabled = bool(state["enabled"])
        if "state_data" in state:
            self._state_data = dict(state["state_data"])
        if "last_signal_time" in state and state["last_signal_time"]:
            self._last_signal_time = datetime.fromisoformat(
                state["last_signal_time"].replace("Z", "+00:00")
            )

    def to_strategy_state(self) -> StrategyState:
        """Convert to a StrategyState model for registry persistence."""
        return StrategyState(
            name=self.name,
            strategy_type=self.strategy_type,
            parameters=self.get_parameters(),
            enabled=self._enabled,
            state_data=self._state_data,
            last_updated=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_feature(features: dict[str, float | None], name: str) -> float | None:
        """Safely retrieve a feature value, returning None if missing or NaN."""
        value = features.get(name)
        if value is None:
            return None
        try:
            import math
            if isinstance(value, float) and math.isnan(value):
                return None
        except (TypeError, ValueError):
            return None
        return float(value)

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        """Clamp confidence to [0, 1]."""
        return max(0.0, min(1.0, float(value)))

    def _create_signal(
        self,
        direction: SignalDirection,
        confidence: float,
        reason: str,
        features: dict[str, float | None],
    ) -> StrategySignal:
        """Create a standardized StrategySignal."""
        now = datetime.now(timezone.utc)
        self._last_signal_time = now
        # Filter features to only include those actually used
        used_features = {
            k: v for k, v in features.items()
            if v is not None and not (isinstance(v, float) and __import__("math").isnan(v))
        }
        return StrategySignal(
            symbol=self.config.symbol,
            direction=direction,
            confidence=self._clamp_confidence(confidence),
            reason=reason,
            features_used=used_features,
            strategy_name=self.name,
            parameters_used=self.get_parameters(),
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_defaults(self) -> None:
        """Apply default parameter values. Override in subclasses."""

    def _validate_parameters(self, params: dict[str, float]) -> None:
        """Validate parameters. Override for custom validation."""
        bounds = self.parameter_bounds()
        for key, value in params.items():
            if key not in bounds:
                continue
            min_val, max_val = bounds[key]
            if not (min_val <= value <= max_val):
                raise ValueError(
                    f"Parameter '{key}'={value} out of bounds [{min_val}, {max_val}]"
                )

    def __getstate__(self) -> dict[str, Any]:
        """Custom pickle serialization for hot-swap support."""
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "config": self.config.model_dump(),
            "parameters": self.get_parameters(),
            "enabled": self._enabled,
            "state_data": self._state_data,
            "last_signal_time": self._last_signal_time.isoformat()
            if self._last_signal_time
            else None,
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Custom pickle deserialization for hot-swap support."""
        self.name = state.get("name", "unknown")
        self.strategy_type = StrategyType(state.get("strategy_type", "trend_following"))
        self.config = StrategyConfig(**state["config"])
        self.parameters = dict(state.get("parameters", {}))
        self._enabled = state.get("enabled", True)
        self._state_data = state.get("state_data", {})
        self._initialized = False
        lst = state.get("last_signal_time")
        self._last_signal_time = datetime.fromisoformat(lst.replace("Z", "+00:00")) if lst else None

    def __reduce__(self) -> tuple:
        """Support pickle by returning a reconstruction tuple."""
        return (_unpickle_strategy, (self.__getstate__(),))


def _unpickle_strategy(state: dict[str, Any]) -> BaseStrategy:
    """Reconstruct a strategy from its pickled state.

    This creates a minimal BaseStrategy instance and restores state.
    Concrete strategies should override this via registry lookup.
    """
    from trading.schemas import StrategyConfig, StrategyType

    config = StrategyConfig(**state["config"])
    # Create a minimal concrete instance
    strategy = _MinimalConcreteStrategy(config)
    strategy.__setstate__(state)
    return strategy


class _MinimalConcreteStrategy(BaseStrategy):
    """Minimal concrete strategy for unpickling base strategies."""

    name = "unpickled"

    def generate_signal(
        self,
        ohlcv_df: pd.DataFrame,
        features: dict[str, float | None],
    ) -> StrategySignal | None:
        return None

    def parameter_bounds(self) -> dict[str, tuple[float, float]]:
        return {}
