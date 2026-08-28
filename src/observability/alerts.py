"""Alert management with configurable rules and severity levels.

Implements 22 pre-configured alerts covering system health, trading,
risk, and data quality.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable


class AlertSeverity(Enum):
    """Alert severity levels."""

    CRITICAL = auto()  # Immediate action required (kill switch)
    HIGH = auto()      # Urgent attention needed
    MEDIUM = auto()    # Should be investigated soon
    LOW = auto()       # Informational, monitor


class AlertState(Enum):
    """Current state of an alert."""

    OK = auto()         # Condition not triggered
    PENDING = auto()    # Condition met, waiting for cooldown
    FIRING = auto()     # Alert is active
    RESOLVED = auto()   # Was firing, now OK


@dataclass(frozen=True)
class AlertRule:
    """Definition of an alert condition."""

    name: str
    description: str
    severity: AlertSeverity
    metric_name: str
    condition: str  # ">", "<", "==", ">=", "<="
    threshold: float
    duration_seconds: float = 0.0  # Must breach for this long
    cooldown_seconds: float = 300.0  # Min time between firings
    auto_resolve: bool = True


@dataclass
class AlertEvent:
    """An instance of an alert firing or resolving."""

    rule_name: str
    severity: AlertSeverity
    state: AlertState
    message: str
    value: float
    threshold: float
    timestamp: float = field(default_factory=time.time)
    resolved_at: float | None = None


class AlertManager:
    """Manages alert rules, evaluation, and notification.

    Pre-configured with 22 standard alerts for trading systems:
    - System health (CPU, memory, disk, latency)
    - Trading (order failures, fill rates, slippage)
    - Risk (drawdown, VaR, exposure)
    - Data (stale prices, feed health)
    """

    # Pre-configured alert definitions
    DEFAULT_RULES: list[AlertRule] = [
        # System Health (4 alerts)
        AlertRule("cpu_usage_high", "CPU usage above 80%", AlertSeverity.HIGH, "system.cpu_percent", ">", 80.0, duration_seconds=60),
        AlertRule("memory_usage_high", "Memory usage above 85%", AlertSeverity.HIGH, "system.memory_percent", ">", 85.0, duration_seconds=60),
        AlertRule("disk_usage_high", "Disk usage above 90%", AlertSeverity.MEDIUM, "system.disk_percent", ">", 90.0, duration_seconds=300),
        AlertRule("service_restart", "Service restarted unexpectedly", AlertSeverity.MEDIUM, "system.restart_count", ">", 0, cooldown_seconds=600),
        # Trading (6 alerts)
        AlertRule("order_rejection_rate", "Order rejection rate above 5%", AlertSeverity.HIGH, "trading.rejection_rate", ">", 0.05, duration_seconds=120),
        AlertRule("fill_rate_low", "Fill rate below 70%", AlertSeverity.MEDIUM, "trading.fill_rate", "<", 0.70, duration_seconds=180),
        AlertRule("slippage_high", "Average slippage above 50 bps", AlertSeverity.HIGH, "trading.avg_slippage_bps", ">", 50.0, duration_seconds=60),
        AlertRule("order_latency_high", "Order latency above 100ms", AlertSeverity.MEDIUM, "trading.order_latency_ms", ">", 100.0, duration_seconds=60),
        AlertRule("position_imbalance", "Long/short imbalance above 80%", AlertSeverity.MEDIUM, "trading.position_imbalance", ">", 0.80, duration_seconds=300),
        AlertRule("unfilled_orders", "More than 10 unfilled orders", AlertSeverity.LOW, "trading.unfilled_count", ">", 10, duration_seconds=60),
        # Risk (6 alerts)
        AlertRule("max_drawdown_breach", "Drawdown exceeded 10%", AlertSeverity.CRITICAL, "risk.max_drawdown", ">", 0.10, duration_seconds=0),
        AlertRule("daily_loss_limit", "Daily loss exceeded 5%", AlertSeverity.CRITICAL, "risk.daily_loss_pct", ">", 0.05, duration_seconds=0),
        AlertRule("var_breach", "95% VaR exceeded", AlertSeverity.HIGH, "risk.var_95", ">", 1.0, duration_seconds=0),
        AlertRule("leverage_high", "Portfolio leverage above 2x", AlertSeverity.HIGH, "risk.leverage", ">", 2.0, duration_seconds=60),
        AlertRule("concentration_risk", "Single position above 25%", AlertSeverity.MEDIUM, "risk.max_position_pct", ">", 0.25, duration_seconds=300),
        AlertRule("kill_switch_triggered", "Kill switch activated", AlertSeverity.CRITICAL, "risk.kill_switch_active", "==", 1.0, duration_seconds=0, cooldown_seconds=0),
        # Data (6 alerts)
        AlertRule("price_stale", "Price data stale > 60s", AlertSeverity.HIGH, "data.price_staleness_sec", ">", 60.0, duration_seconds=30),
        AlertRule("feed_disconnected", "Market feed disconnected", AlertSeverity.CRITICAL, "data.feed_connected", "==", 0.0, duration_seconds=0),
        AlertRule("data_quality_error", "Data quality score below 95%", AlertSeverity.HIGH, "data.quality_score", "<", 0.95, duration_seconds=120),
        AlertRule("missing_tickers", "Missing data for > 5 tickers", AlertSeverity.MEDIUM, "data.missing_tickers", ">", 5, duration_seconds=180),
        AlertRule("backfill_lag", "Backfill lag > 5 minutes", AlertSeverity.LOW, "data.backfill_lag_sec", ">", 300.0, duration_seconds=300),
        AlertRule("database_slow", "DB query latency > 500ms", AlertSeverity.MEDIUM, "data.db_latency_ms", ">", 500.0, duration_seconds=60),
    ]

    def __init__(self, rules: list[AlertRule] | None = None):
        """Initialize alert manager.

        Args:
            rules: Alert rules. Uses DEFAULT_RULES if not provided.
        """
        self.rules: dict[str, AlertRule] = {r.name: r for r in (rules or self.DEFAULT_RULES)}
        self._state: dict[str, AlertState] = {name: AlertState.OK for name in self.rules}
        self._first_breach: dict[str, float] = {}
        self._last_firing: dict[str, float] = {}
        self._events: list[AlertEvent] = []
        self._lock = threading.RLock()
        self._callbacks: list[Callable[[AlertEvent], None]] = []
        self._suppressed: set[str] = set()

    def evaluate(self, metric_name: str, value: float) -> list[AlertEvent]:
        """Evaluate all rules against a metric value.

        Args:
            metric_name: Name of the metric.
            value: Current metric value.

        Returns:
            List of alert events generated (empty if no alerts).
        """
        events: list[AlertEvent] = []
        now = time.time()

        # Find rules that monitor this metric
        matching = [r for r in self.rules.values() if r.metric_name == metric_name]

        for rule in matching:
            if rule.name in self._suppressed:
                continue

            breached = self._check_condition(value, rule.condition, rule.threshold)
            current_state = self._state.get(rule.name, AlertState.OK)

            with self._lock:
                if breached:
                    if current_state == AlertState.OK:
                        # First breach
                        self._first_breach[rule.name] = now
                        # If no duration required, fire immediately
                        if rule.duration_seconds <= 0:
                            last = self._last_firing.get(rule.name, 0)
                            if now - last >= rule.cooldown_seconds:
                                self._state[rule.name] = AlertState.FIRING
                                self._last_firing[rule.name] = now
                                event = AlertEvent(
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    state=AlertState.FIRING,
                                    message=f"{rule.description}: {value:.4f} (threshold: {rule.threshold})",
                                    value=value,
                                    threshold=rule.threshold,
                                )
                                self._events.append(event)
                                events.append(event)
                                self._notify(event)
                        else:
                            self._state[rule.name] = AlertState.PENDING
                    elif current_state == AlertState.PENDING:
                        # Check duration
                        elapsed = now - self._first_breach.get(rule.name, now)
                        if elapsed >= rule.duration_seconds:
                            # Check cooldown
                            last = self._last_firing.get(rule.name, 0)
                            if now - last >= rule.cooldown_seconds:
                                self._state[rule.name] = AlertState.FIRING
                                self._last_firing[rule.name] = now
                                event = AlertEvent(
                                    rule_name=rule.name,
                                    severity=rule.severity,
                                    state=AlertState.FIRING,
                                    message=f"{rule.description}: {value:.4f} (threshold: {rule.threshold})",
                                    value=value,
                                    threshold=rule.threshold,
                                )
                                self._events.append(event)
                                events.append(event)
                                self._notify(event)
                else:
                    # Value is OK
                    if current_state == AlertState.FIRING and rule.auto_resolve:
                        self._state[rule.name] = AlertState.RESOLVED
                        event = AlertEvent(
                            rule_name=rule.name,
                            severity=rule.severity,
                            state=AlertState.RESOLVED,
                            message=f"{rule.description} resolved: {value:.4f}",
                            value=value,
                            threshold=rule.threshold,
                            resolved_at=now,
                        )
                        self._events.append(event)
                        events.append(event)
                        self._notify(event)
                    elif current_state != AlertState.OK:
                        self._state[rule.name] = AlertState.OK
                        self._first_breach.pop(rule.name, None)

        return events

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        """Check if value meets condition against threshold."""
        match condition:
            case ">":
                return value > threshold
            case "<":
                return value < threshold
            case "==":
                return value == threshold
            case ">=":
                return value >= threshold
            case "<=":
                return value <= threshold
            case _:
                return False

    def suppress(self, rule_name: str) -> None:
        """Suppress an alert rule."""
        self._suppressed.add(rule_name)

    def unsuppress(self, rule_name: str) -> None:
        """Unsuppress an alert rule."""
        self._suppressed.discard(rule_name)

    def get_active_alerts(self) -> list[AlertEvent]:
        """Return currently firing alerts."""
        with self._lock:
            return [
                e for e in self._events
                if e.state == AlertState.FIRING
            ]

    def get_alert_history(
        self,
        rule_name: str | None = None,
        severity: AlertSeverity | None = None,
    ) -> list[AlertEvent]:
        """Return alert history with optional filtering."""
        with self._lock:
            events = self._events.copy()
        if rule_name:
            events = [e for e in events if e.rule_name == rule_name]
        if severity:
            events = [e for e in events if e.severity == severity]
        return events

    def clear_history(self) -> None:
        """Clear alert history."""
        with self._lock:
            self._events.clear()

    def get_status(self) -> dict[str, AlertState]:
        """Return current state of all alert rules."""
        with self._lock:
            return self._state.copy()

    def get_firing_count(self) -> int:
        """Count currently firing alerts."""
        return sum(1 for s in self._state.values() if s == AlertState.FIRING)

    def on_alert(self, callback: Callable[[AlertEvent], None]) -> None:
        """Register alert event callback."""
        self._callbacks.append(callback)

    def _notify(self, event: AlertEvent) -> None:
        """Notify all callbacks."""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass

    @property
    def firing_alerts(self) -> list[str]:
        """Names of currently firing alerts."""
        return [name for name, state in self._state.items() if state == AlertState.FIRING]

    @property
    def rule_count(self) -> int:
        """Total number of configured rules."""
        return len(self.rules)
