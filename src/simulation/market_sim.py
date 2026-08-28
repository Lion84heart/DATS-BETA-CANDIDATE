"""Market price simulation for backtesting and E2E testing.

Provides synthetic price paths using geometric Brownian motion
and configurable market regimes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterator


@dataclass
class PricePath:
    """A generated price path with metadata."""

    symbol: str
    prices: list[float]
    timestamps: list[float]
    volatility: float
    drift: float

    @property
    def returns(self) -> list[float]:
        """Calculate log returns."""
        if len(self.prices) < 2:
            return []
        return [
            math.log(self.prices[i] / self.prices[i - 1])
            for i in range(1, len(self.prices))
        ]

    @property
    def final_price(self) -> float:
        return self.prices[-1] if self.prices else 0.0

    @property
    def max_price(self) -> float:
        return max(self.prices) if self.prices else 0.0

    @property
    def min_price(self) -> float:
        return min(self.prices) if self.prices else 0.0


class MarketSimulator:
    """Generates synthetic price paths for simulation.

    Uses geometric Brownian motion with configurable drift,
    volatility, and optional regime shifts.
    """

    def __init__(
        self,
        seed: int | None = None,
        default_volatility: float = 0.02,
        default_drift: float = 0.0001,
    ):
        """Initialize market simulator.

        Args:
            seed: Random seed for reproducibility.
            default_volatility: Daily volatility (e.g., 0.02 = 2%).
            default_drift: Daily drift (e.g., 0.0001 = 0.01%).
        """
        self._rng = random.Random(seed)
        self.default_volatility = default_volatility
        self.default_drift = default_drift

    def generate_path(
        self,
        symbol: str,
        start_price: float,
        steps: int,
        timestep_days: float = 1.0,
        volatility: float | None = None,
        drift: float | None = None,
    ) -> PricePath:
        """Generate a price path using geometric Brownian motion.

        Args:
            symbol: Asset symbol.
            start_price: Initial price.
            steps: Number of time steps.
            timestep_days: Fraction of a day per step.
            volatility: Override default volatility.
            drift: Override default drift.

        Returns:
            PricePath with generated prices.
        """
        vol = volatility if volatility is not None else self.default_volatility
        drift_rate = drift if drift is not None else self.default_drift

        prices: list[float] = [start_price]
        timestamps: list[float] = [0.0]
        dt = timestep_days

        for step in range(1, steps + 1):
            prev = prices[-1]
            z = self._rng.gauss(0, 1)
            change = (drift_rate - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z
            new_price = prev * math.exp(change)
            prices.append(max(new_price, 0.0001))  # Prevent zero/negative
            timestamps.append(step * dt)

        return PricePath(
            symbol=symbol,
            prices=prices,
            timestamps=timestamps,
            volatility=vol,
            drift=drift_rate,
        )

    def generate_multi_asset(
        self,
        symbols: list[str],
        start_prices: dict[str, float],
        steps: int,
        correlation_matrix: dict[tuple[str, str], float] | None = None,
        timestep_days: float = 1.0,
    ) -> dict[str, PricePath]:
        """Generate correlated price paths for multiple assets.

        Args:
            symbols: List of asset symbols.
            start_prices: Starting price per symbol.
            steps: Number of time steps.
            correlation_matrix: Pairwise correlations (default: uncorrelated).
            timestep_days: Fraction of a day per step.

        Returns:
            Dictionary mapping symbol to PricePath.
        """
        # Cholesky decomposition for correlated random variables
        n = len(symbols)
        corr = correlation_matrix or {}

        # Build correlation matrix
        cov = [[1.0 if i == j else corr.get((symbols[i], symbols[j]), 0.0)
                for j in range(n)] for i in range(n)]

        # Simple Cholesky (assumes positive semi-definite)
        L = self._cholesky(cov)

        # Generate correlated random walks
        price_paths: dict[str, list[float]] = {s: [start_prices[s]] for s in symbols}
        timestamps: list[float] = [0.0]

        dt = timestep_days
        vol = self.default_volatility
        drift_rate = self.default_drift

        for step in range(1, steps + 1):
            # Generate independent standard normals
            z = [self._rng.gauss(0, 1) for _ in range(n)]
            # Correlate via L
            correlated = [sum(L[i][j] * z[j] for j in range(n)) for i in range(n)]

            for i, symbol in enumerate(symbols):
                prev = price_paths[symbol][-1]
                change = (drift_rate - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * correlated[i]
                new_price = prev * math.exp(change)
                price_paths[symbol].append(max(new_price, 0.0001))

            timestamps.append(step * dt)

        return {
            symbol: PricePath(
                symbol=symbol,
                prices=price_paths[symbol],
                timestamps=timestamps,
                volatility=vol,
                drift=drift_rate,
            )
            for symbol in symbols
        }

    def _cholesky(self, matrix: list[list[float]]) -> list[list[float]]:
        """Simple Cholesky decomposition."""
        n = len(matrix)
        L = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1):
                s = sum(L[i][k] * L[j][k] for k in range(j))
                if i == j:
                    val = matrix[i][i] - s
                    L[i][j] = math.sqrt(max(val, 0.0))
                else:
                    if L[j][j] > 0:
                        L[i][j] = (matrix[i][j] - s) / L[j][j]
        return L

    def stream_prices(
        self,
        symbol: str,
        start_price: float,
        volatility: float | None = None,
    ) -> Iterator[tuple[float, float]]:
        """Generate an infinite stream of (timestamp, price) tuples.

        Args:
            symbol: Asset symbol.
            start_price: Initial price.
            volatility: Override default volatility.

        Yields:
            (timestamp, price) tuples.
        """
        price = start_price
        vol = volatility if volatility is not None else self.default_volatility
        drift_rate = self.default_drift
        dt = 1.0 / 390  # 1-minute bars (390 per trading day)
        step = 0

        while True:
            z = self._rng.gauss(0, 1)
            change = (drift_rate - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * z
            price = price * math.exp(change)
            price = max(price, 0.0001)
            step += 1
            yield step * dt, price
