"""Health checks and readiness probes for services.

Implements liveness and readiness checks with configurable
dependencies and timeout handling.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Awaitable, Callable


class HealthStatus(Enum):
    """Health status of a component or service."""

    HEALTHY = auto()
    DEGRADED = auto()
    UNHEALTHY = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: HealthStatus
    response_time_ms: float
    message: str
    timestamp: float
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class ServiceHealth:
    """Aggregated health of a service."""

    service_name: str
    overall_status: HealthStatus
    checks: list[HealthCheckResult]
    uptime_seconds: float
    timestamp: float


class HealthCheck:
    """Health check manager with async support.

    Supports both synchronous and asynchronous check functions
    with configurable timeouts.
    """

    def __init__(self, service_name: str, timeout_seconds: float = 5.0):
        """Initialize health check manager.

        Args:
            service_name: Name of the service being checked.
            timeout_seconds: Default timeout for checks.
        """
        self.service_name = service_name
        self.timeout_seconds = timeout_seconds
        self._checks: dict[str, Callable[[], HealthCheckResult | Awaitable[HealthCheckResult]]] = {}
        self._metadata: dict[str, str] = {}
        self._start_time = time.time()

    def register(
        self,
        name: str,
        check_fn: Callable[[], HealthCheckResult | Awaitable[HealthCheckResult]],
    ) -> None:
        """Register a health check.

        Args:
            name: Check name.
            check_fn: Function returning HealthCheckResult or awaitable.
        """
        self._checks[name] = check_fn

    def set_metadata(self, **kwargs: str) -> None:
        """Set service metadata."""
        self._metadata.update(kwargs)

    async def run(self, check_name: str | None = None) -> ServiceHealth:
        """Run health checks.

        Args:
            check_name: Optional single check to run. Runs all if None.

        Returns:
            ServiceHealth with aggregated results.
        """
        names = [check_name] if check_name else list(self._checks.keys())
        results: list[HealthCheckResult] = []

        for name in names:
            if name not in self._checks:
                results.append(
                    HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNKNOWN,
                        response_time_ms=0.0,
                        message=f"Check '{name}' not registered",
                        timestamp=time.time(),
                    )
                )
                continue

            t0 = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    self._await_check(self._checks[name]()),
                    timeout=self.timeout_seconds,
                )
                # Normalize tuple returns to HealthCheckResult
                if isinstance(result, tuple):
                    healthy = bool(result[0]) if result else False
                    message = str(result[1]) if len(result) > 1 else ""
                    results.append(
                        HealthCheckResult(
                            name=name,
                            status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
                            response_time_ms=(time.perf_counter() - t0) * 1000,
                            message=message,
                            timestamp=time.time(),
                        )
                    )
                elif isinstance(result, HealthCheckResult):
                    results.append(result)
                else:
                    results.append(
                        HealthCheckResult(
                            name=name,
                            status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                            response_time_ms=(time.perf_counter() - t0) * 1000,
                            message=str(result) if result else "",
                            timestamp=time.time(),
                        )
                    )
            except asyncio.TimeoutError:
                results.append(
                    HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=(time.perf_counter() - t0) * 1000,
                        message=f"Check timed out after {self.timeout_seconds}s",
                        timestamp=time.time(),
                    )
                )
            except Exception as e:
                results.append(
                    HealthCheckResult(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=(time.perf_counter() - t0) * 1000,
                        message=f"Check failed: {e}",
                        timestamp=time.time(),
                    )
                )

        # Determine overall status
        statuses = [r.status for r in results]
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses) and statuses:
            overall = HealthStatus.HEALTHY
        else:
            overall = HealthStatus.UNKNOWN

        return ServiceHealth(
            service_name=self.service_name,
            overall_status=overall,
            checks=results,
            uptime_seconds=time.time() - self._start_time,
            timestamp=time.time(),
        )

    @staticmethod
    async def _await_check(
        result: HealthCheckResult | Awaitable[HealthCheckResult],
    ) -> HealthCheckResult:
        """Await if the result is a coroutine."""
        if asyncio.iscoroutine(result):
            return await result
        return result

    @property
    def check_names(self) -> list[str]:
        """Return names of registered checks."""
        return list(self._checks.keys())


def simple_check(name: str, healthy: bool, message: str = "") -> HealthCheckResult:
    """Create a simple health check result.

    Args:
        name: Check name.
        healthy: Whether the check passes.
        message: Optional message.

    Returns:
        HealthCheckResult.
    """
    return HealthCheckResult(
        name=name,
        status=HealthStatus.HEALTHY if healthy else HealthStatus.UNHEALTHY,
        response_time_ms=0.0,
        message=message or ("OK" if healthy else "Failed"),
        timestamp=time.time(),
    )
