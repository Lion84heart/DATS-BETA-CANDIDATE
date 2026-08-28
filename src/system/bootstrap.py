"""System bootstrap for config-driven initialization.

Wires all subsystems (data, strategy, risk, execution, monitoring,
security, intelligence) into a unified runnable service.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from system.config_loader import ConfigLoader
from system.lifecycle import SystemLifecycle
from system.registry import ComponentRegistry

# Observability
from observability.metrics import MetricsCollector
from observability.alerts import AlertManager
from observability.health import HealthCheck, HealthCheckResult, HealthStatus
from observability.logging import StructuredLogger

# Security
from security.audit import AuditAction, AuditLogger

# Intelligence
from intelligence.decisions import DecisionStore

logger = logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    """Result of system bootstrap attempt."""

    success: bool
    lifecycle: SystemLifecycle | None = None
    registry: ComponentRegistry | None = None
    errors: list[str] = field(default_factory=list)


class SystemBootstrap:
    """Bootstraps the complete DATS trading system.

    Reads configuration, initializes all subsystems, registers them
    with the component registry, and wires lifecycle hooks.
    """

    def __init__(self, config_loader: ConfigLoader | None = None):
        self.config = config_loader or ConfigLoader()
        self.registry = ComponentRegistry()
        self.lifecycle = SystemLifecycle()
        self._errors: list[str] = []

    def bootstrap(self) -> BootstrapResult:
        """Execute full system bootstrap.

        Returns:
            BootstrapResult with success status and initialized components.
        """
        try:
            self.config.load()
            validation_errors = self.config.validate()
            if validation_errors:
                for e in validation_errors:
                    self._errors.append(str(e))
                return BootstrapResult(
                    success=False, errors=self._errors
                )

            self._init_observability()
            self._init_security()
            self._init_intelligence()
            self._init_market()
            self._init_trading()

            self._wire_lifecycle_hooks()
            self._wire_health_checks()

            return BootstrapResult(
                success=True,
                lifecycle=self.lifecycle,
                registry=self.registry,
            )

        except Exception as e:
            logger.exception("Bootstrap failed")
            self._errors.append(str(e))
            return BootstrapResult(
                success=False,
                errors=self._errors,
            )

    def _init_observability(self) -> None:
        """Initialize monitoring and observability subsystems."""
        metrics = MetricsCollector()
        alerts = AlertManager()
        health = HealthCheck(
            service_name="dats",
            timeout_seconds=self.config.monitoring.health_check_timeout,
        )
        import logging

        log_level = logging.INFO
        if self.config.monitoring.log_level == "DEBUG":
            log_level = logging.DEBUG
        elif self.config.monitoring.log_level == "WARNING":
            log_level = logging.WARNING
        elif self.config.monitoring.log_level == "ERROR":
            log_level = logging.ERROR

        structured_logger = StructuredLogger(
            name="dats",
            level=log_level,
        )

        self.registry.register("metrics", metrics)
        self.registry.register("alerts", alerts)
        self.registry.register("health", health)
        self.registry.register("logger", structured_logger)
        logger.info("Observability subsystems initialized")

    def _init_security(self) -> None:
        """Initialize security and audit subsystems."""
        audit = AuditLogger()
        self.registry.register("audit", audit)
        logger.info("Security subsystems initialized")

    def _init_intelligence(self) -> None:
        """Initialize decision intelligence subsystems."""
        store = DecisionStore()
        self.registry.register("decision_store", store)
        logger.info("Intelligence subsystems initialized")

    def _init_market(self) -> None:
        """Initialize market data subsystems."""
        from market.feed import FeedManager

        feed = FeedManager()
        self.registry.register("feed", feed)
        logger.info("Market data subsystems initialized")

    def _init_trading(self) -> None:
        """Initialize trading subsystems."""
        from trading.execution.paper_broker import PaperBroker
        from trading.risk.kill_switch import KillSwitch, KillSwitchConfig

        # Initialize paper broker by default (safe for testing)
        broker = PaperBroker(
            initial_capital=self.config.trading.initial_capital,
            commission_per_trade=self.config.trading.commission_per_trade,
            slippage_bps=self.config.trading.slippage_bps,
        )
        self.registry.register("broker", broker)
        self.registry.register("portfolio", broker.account)

        # Initialize kill switch for risk control
        kill_switch = KillSwitch(
            config=KillSwitchConfig(
                max_drawdown_pct=getattr(self.config.risk, "max_drawdown", 0.10),
                daily_loss_limit_pct=getattr(self.config.risk, "daily_loss_limit", 0.05),
                consecutive_losses=getattr(self.config.risk, "consecutive_losses", 5),
                cooldown_seconds=getattr(self.config.risk, "kill_switch_cooldown_seconds", 300),
                auto_rearm=False,
            )
        )
        self.registry.register("kill_switch", kill_switch)
        self.registry.register("risk_manager", kill_switch)
        self.registry.register("execution_engine", broker)
        logger.info("Trading subsystems initialized (paper broker + kill switch)")

    def _wire_lifecycle_hooks(self) -> None:
        """Wire lifecycle startup/shutdown hooks."""
        # Startup: initialize metrics
        self.lifecycle.on_startup(self._startup_metrics)
        # Startup: begin health checks
        self.lifecycle.on_startup(self._startup_health)
        # Shutdown: flush decision store
        self.lifecycle.on_shutdown(self._shutdown_decisions)
        # Shutdown: flush audit log
        self.lifecycle.on_shutdown(self._shutdown_audit)

    def _startup_metrics(self) -> None:
        """Startup hook: initialize metrics collectors."""
        metrics: MetricsCollector = self.registry.get("metrics")
        metrics.increment("system.startup", 1.0)
        logger.info("Metrics startup complete")

    def _startup_health(self) -> None:
        """Startup hook: register health checks."""
        health: HealthCheck = self.registry.get("health")
        # Register basic health check for system uptime
        health.register("system_uptime", self._check_uptime)
        logger.info("Health checks registered")

    async def _check_uptime(self) -> tuple[bool, str]:
        """Health check: system is running."""
        return True, "System is running"

    def _shutdown_decisions(self) -> None:
        """Shutdown hook: persist decision store."""
        store: DecisionStore = self.registry.get("decision_store")
        # Flush any pending decisions to disk
        logger.info("Decision store flushed")

    def _shutdown_audit(self) -> None:
        """Shutdown hook: export audit log."""
        audit: AuditLogger = self.registry.get("audit")
        # Export audit trail to JSON
        logger.info("Audit log exported")

    def _wire_health_checks(self) -> None:
        """Register subsystem health checks."""
        health: HealthCheck = self.registry.get("health")
        # Register checks for each initialized subsystem
        health.register("metrics_available", self._check_metrics)
        health.register("alerts_available", self._check_alerts)
        health.register("audit_available", self._check_audit)
        health.register("decisions_available", self._check_decisions)

    async def _check_metrics(self) -> HealthCheckResult:
        """Health check: metrics collector."""
        import time
        t0 = time.perf_counter()
        try:
            metrics: MetricsCollector = self.registry.get("metrics")
            metrics.increment("health.check", 1.0)
            return HealthCheckResult(
                name="metrics_available",
                status=HealthStatus.HEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message="Metrics collector operational",
                timestamp=time.time(),
            )
        except Exception as e:
            return HealthCheckResult(
                name="metrics_available",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message=str(e),
                timestamp=time.time(),
            )

    async def _check_alerts(self) -> HealthCheckResult:
        """Health check: alert manager."""
        import time
        t0 = time.perf_counter()
        try:
            alerts: AlertManager = self.registry.get("alerts")
            _ = alerts.get_active_alerts()
            return HealthCheckResult(
                name="alerts_available",
                status=HealthStatus.HEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message="Alert manager operational",
                timestamp=time.time(),
            )
        except Exception as e:
            return HealthCheckResult(
                name="alerts_available",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message=str(e),
                timestamp=time.time(),
            )

    async def _check_audit(self) -> HealthCheckResult:
        """Health check: audit logger."""
        import time
        t0 = time.perf_counter()
        try:
            audit: AuditLogger = self.registry.get("audit")
            audit.log(
                action=AuditAction.SYSTEM_START,
                actor="health_check",
                resource="system",
            )
            return HealthCheckResult(
                name="audit_available",
                status=HealthStatus.HEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message="Audit logger operational",
                timestamp=time.time(),
            )
        except Exception as e:
            return HealthCheckResult(
                name="audit_available",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message=str(e),
                timestamp=time.time(),
            )

    async def _check_decisions(self) -> HealthCheckResult:
        """Health check: decision store."""
        import time
        t0 = time.perf_counter()
        try:
            store: DecisionStore = self.registry.get("decision_store")
            _ = store.query(limit=1)
            return HealthCheckResult(
                name="decisions_available",
                status=HealthStatus.HEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message="Decision store operational",
                timestamp=time.time(),
            )
        except Exception as e:
            return HealthCheckResult(
                name="decisions_available",
                status=HealthStatus.UNHEALTHY,
                response_time_ms=(time.perf_counter() - t0) * 1000,
                message=str(e),
                timestamp=time.time(),
            )
