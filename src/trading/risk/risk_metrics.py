"""Risk metrics calculation for trading portfolios.

Implements Value at Risk (VaR), Conditional VaR (CVaR),
drawdown analysis, Sharpe ratio, Sortino ratio, and other
portfolio risk measures.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RiskProfile:
    """Comprehensive risk profile for a strategy or portfolio."""

    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    max_drawdown: float
    avg_drawdown: float
    drawdown_duration: int
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    volatility: float
    downside_deviation: float
    win_rate: float
    profit_factor: float
    expectancy: float


class VaRModel:
    """Value at Risk calculation using multiple methods."""

    def __init__(self, method: str = "historical"):
        """Initialize VaR model.

        Args:
            method: "historical", "parametric", or "monte_carlo".
        """
        if method not in {"historical", "parametric", "monte_carlo"}:
            raise ValueError(f"Unknown VaR method: {method}")
        self.method = method

    def calculate(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
        portfolio_value: float = 1.0,
    ) -> float:
        """Calculate VaR at given confidence level.

        Args:
            returns: Array of returns (as decimals, e.g., 0.01 = 1%).
            confidence: Confidence level (e.g., 0.95 = 95%).
            portfolio_value: Current portfolio value.

        Returns:
            VaR as a positive dollar amount (potential loss).
        """
        if len(returns) == 0:
            raise ValueError("returns array must not be empty")
        if not 0 < confidence < 1:
            raise ValueError("confidence must be in (0, 1)")
        if portfolio_value <= 0:
            raise ValueError("portfolio_value must be positive")

        if self.method == "historical":
            return self._historical_var(returns, confidence, portfolio_value)
        elif self.method == "parametric":
            return self._parametric_var(returns, confidence, portfolio_value)
        else:
            return self._monte_carlo_var(returns, confidence, portfolio_value)

    def _historical_var(
        self, returns: np.ndarray, confidence: float, portfolio_value: float
    ) -> float:
        """Historical simulation VaR."""
        percentile = (1.0 - confidence) * 100.0
        var_return = np.percentile(returns, percentile)
        # var_return is negative for losses; return positive dollar amount
        return abs(var_return) * portfolio_value

    def _parametric_var(
        self, returns: np.ndarray, confidence: float, portfolio_value: float
    ) -> float:
        """Parametric (variance-covariance) VaR."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        z_score = abs(np.percentile(np.random.standard_normal(10000), (1.0 - confidence) * 100))
        # Use exact normal quantile
        from scipy import stats
        z = abs(stats.norm.ppf(1.0 - confidence))
        var_return = mean - z * std
        return abs(var_return) * portfolio_value

    def _monte_carlo_var(
        self, returns: np.ndarray, confidence: float, portfolio_value: float
    ) -> float:
        """Monte Carlo simulation VaR."""
        mean = np.mean(returns)
        std = np.std(returns, ddof=1)
        simulated = np.random.normal(mean, std, 10000)
        percentile = (1.0 - confidence) * 100.0
        var_return = np.percentile(simulated, percentile)
        return abs(var_return) * portfolio_value

    def cvar(
        self,
        returns: np.ndarray,
        confidence: float = 0.95,
        portfolio_value: float = 1.0,
    ) -> float:
        """Calculate Conditional VaR (Expected Shortfall).

        CVaR is the average loss in the tail beyond VaR.
        """
        if len(returns) == 0:
            raise ValueError("returns array must not be empty")
        percentile = (1.0 - confidence) * 100.0
        var_threshold = np.percentile(returns, percentile)
        tail_losses = returns[returns <= var_threshold]
        if len(tail_losses) == 0:
            return 0.0
        return abs(np.mean(tail_losses)) * portfolio_value


class RiskMetrics:
    """Comprehensive risk metrics calculator."""

    def __init__(self, risk_free_rate: float = 0.0):
        """Initialize risk metrics calculator.

        Args:
            risk_free_rate: Annualized risk-free rate (as decimal).
        """
        self.risk_free_rate = risk_free_rate
        self.var_model = VaRModel(method="historical")

    def calculate_profile(
        self,
        returns: np.ndarray,
        portfolio_value: float = 1.0,
    ) -> RiskProfile:
        """Calculate comprehensive risk profile.

        Args:
            returns: Array of period returns (as decimals).
            portfolio_value: Current portfolio value.

        Returns:
            RiskProfile with all metrics.
        """
        if len(returns) == 0:
            raise ValueError("returns array must not be empty")

        # VaR metrics
        var_95 = self.var_model.calculate(returns, 0.95, portfolio_value)
        var_99 = self.var_model.calculate(returns, 0.99, portfolio_value)
        cvar_95 = self.var_model.cvar(returns, 0.95, portfolio_value)
        cvar_99 = self.var_model.cvar(returns, 0.99, portfolio_value)

        # Drawdown metrics
        max_dd, avg_dd, dd_duration = self._drawdown_metrics(returns)

        # Return metrics
        sharpe = self._sharpe_ratio(returns)
        sortino = self._sortino_ratio(returns)
        calmar = self._calmar_ratio(returns, max_dd)
        vol = np.std(returns, ddof=1) * math.sqrt(252) if len(returns) > 1 else 0.0
        downside_dev = self._downside_deviation(returns)

        # Trade metrics
        win_rate = np.mean(returns > 0) if len(returns) > 0 else 0.0
        profit_factor = self._profit_factor(returns)
        expectancy = np.mean(returns) if len(returns) > 0 else 0.0

        return RiskProfile(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            max_drawdown=max_dd,
            avg_drawdown=avg_dd,
            drawdown_duration=dd_duration,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            volatility=vol,
            downside_deviation=downside_dev,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
        )

    def _drawdown_metrics(self, returns: np.ndarray) -> tuple[float, float, int]:
        """Calculate drawdown metrics.

        Returns:
            (max_drawdown, avg_drawdown, max_drawdown_duration)
        """
        # Cumulative returns
        cumulative = np.cumprod(1.0 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max

        max_dd = abs(np.min(drawdowns))
        avg_dd = abs(np.mean(drawdowns[drawdowns < 0])) if np.any(drawdowns < 0) else 0.0

        # Max drawdown duration
        max_duration = 0
        current_duration = 0
        for dd in drawdowns:
            if dd < 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return max_dd, avg_dd, max_duration

    def _sharpe_ratio(self, returns: np.ndarray) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)
        # Handle near-zero std (consistent returns)
        if std_return < 1e-12:
            return float("inf") if mean_return > 0 else 0.0
        # Annualize (assuming daily returns)
        return ((mean_return * 252) - self.risk_free_rate) / (std_return * math.sqrt(252))

    def _sortino_ratio(self, returns: np.ndarray) -> float:
        """Calculate annualized Sortino ratio."""
        if len(returns) < 2:
            return 0.0
        mean_return = np.mean(returns)
        downside = self._downside_deviation(returns)
        if downside == 0:
            return 0.0
        return ((mean_return * 252) - self.risk_free_rate) / (downside * math.sqrt(252))

    def _downside_deviation(self, returns: np.ndarray) -> float:
        """Calculate downside deviation (standard deviation of negative returns)."""
        negative_returns = returns[returns < 0]
        if len(negative_returns) == 0:
            return 0.0
        return np.std(negative_returns, ddof=1)

    def _calmar_ratio(self, returns: np.ndarray, max_drawdown: float) -> float:
        """Calculate Calmar ratio (annualized return / max drawdown)."""
        if max_drawdown == 0:
            return 0.0
        annualized_return = np.mean(returns) * 252
        return annualized_return / max_drawdown

    def _profit_factor(self, returns: np.ndarray) -> float:
        """Calculate profit factor (gross profits / gross losses)."""
        gross_profits = np.sum(returns[returns > 0])
        gross_losses = abs(np.sum(returns[returns < 0]))
        if gross_losses == 0:
            return float("inf") if gross_profits > 0 else 0.0
        return gross_profits / gross_losses

    def rolling_var(
        self,
        returns: np.ndarray,
        window: int = 20,
        confidence: float = 0.95,
    ) -> np.ndarray:
        """Calculate rolling VaR over a moving window.

        Args:
            returns: Array of returns.
            window: Rolling window size.
            confidence: Confidence level.

        Returns:
            Array of rolling VaR values.
        """
        if len(returns) < window:
            return np.array([])
        result = np.full(len(returns), np.nan)
        percentile = (1.0 - confidence) * 100.0
        for i in range(window, len(returns) + 1):
            window_returns = returns[i - window:i]
            result[i - 1] = abs(np.percentile(window_returns, percentile))
        return result
