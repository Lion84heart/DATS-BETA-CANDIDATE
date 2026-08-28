"""Rate limiting with token bucket algorithm.

Prevents abuse of trading APIs and internal services through
configurable rate limits per client/API key.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TokenBucket:
    """Token bucket for rate limiting.

    Supports burst capacity and refill rate.
    """

    capacity: float  # Maximum tokens (burst size)
    refill_rate: float  # Tokens per second
    _tokens: float = 0.0
    _last_refill: float = 0.0
    _lock: threading.Lock = None

    def __post_init__(self):
        if self._lock is None:
            self._lock = threading.Lock()
        self._tokens = self.capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Add tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens.

        Args:
            tokens: Number of tokens to consume.

        Returns:
            True if tokens were available, False if rate limited.
        """
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self, tokens: float = 1.0) -> float:
        """Calculate wait time until tokens are available.

        Args:
            tokens: Number of tokens needed.

        Returns:
            Seconds to wait (0.0 if available now).
        """
        with self._lock:
            self._refill()
            deficit = tokens - self._tokens
            if deficit <= 0:
                return 0.0
            return deficit / self.refill_rate


class RateLimiter:
    """Multi-key rate limiter using token buckets.

    Manages independent rate limits for multiple clients,
    API keys, or endpoints.
    """

    def __init__(
        self,
        default_capacity: float = 10.0,
        default_refill_rate: float = 1.0,
        cleanup_interval: float = 300.0,
    ):
        """Initialize rate limiter.

        Args:
            default_capacity: Default burst capacity.
            default_refill_rate: Default tokens per second.
            cleanup_interval: Seconds between stale bucket cleanup.
        """
        self.default_capacity = default_capacity
        self.default_refill_rate = default_refill_rate
        self.cleanup_interval = cleanup_interval
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.RLock()
        self._last_access: dict[str, float] = {}
        self._last_cleanup = time.monotonic()

    def is_allowed(
        self,
        key: str,
        tokens: float = 1.0,
        capacity: float | None = None,
        refill_rate: float | None = None,
    ) -> bool:
        """Check if a request is allowed under rate limit.

        Args:
            key: Rate limit bucket identifier (e.g., API key).
            tokens: Tokens to consume.
            capacity: Override default capacity.
            refill_rate: Override default refill rate.

        Returns:
            True if request is allowed.
        """
        self._maybe_cleanup()
        bucket = self._get_bucket(key, capacity, refill_rate)
        allowed = bucket.consume(tokens)
        with self._lock:
            self._last_access[key] = time.monotonic()
        return allowed

    def check(
        self,
        key: str,
        tokens: float = 1.0,
        capacity: float | None = None,
        refill_rate: float | None = None,
    ) -> tuple[bool, float]:
        """Check rate limit and return retry-after if limited.

        Args:
            key: Rate limit bucket identifier.
            tokens: Tokens to consume.
            capacity: Override default capacity.
            refill_rate: Override default refill rate.

        Returns:
            (allowed, retry_after_seconds)
        """
        self._maybe_cleanup()
        bucket = self._get_bucket(key, capacity, refill_rate)
        allowed = bucket.consume(tokens)
        with self._lock:
            self._last_access[key] = time.monotonic()
        retry_after = 0.0 if allowed else bucket.wait_time(tokens)
        return allowed, retry_after

    def _get_bucket(
        self,
        key: str,
        capacity: float | None,
        refill_rate: float | None,
    ) -> TokenBucket:
        """Get or create bucket for key."""
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    capacity=capacity or self.default_capacity,
                    refill_rate=refill_rate or self.default_refill_rate,
                )
            return self._buckets[key]

    def _maybe_cleanup(self) -> None:
        """Remove stale buckets periodically."""
        now = time.monotonic()
        if now - self._last_cleanup < self.cleanup_interval:
            return
        with self._lock:
            stale = [
                k for k, last in self._last_access.items()
                if now - last > self.cleanup_interval * 2
            ]
            for k in stale:
                self._buckets.pop(k, None)
                self._last_access.pop(k, None)
            self._last_cleanup = now

    def reset(self, key: str) -> None:
        """Reset rate limit for a key."""
        with self._lock:
            self._buckets.pop(key, None)
            self._last_access.pop(key, None)

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Get current status of all buckets."""
        with self._lock:
            return {
                k: {
                    "capacity": b.capacity,
                    "refill_rate": b.refill_rate,
                    "tokens": b._tokens,
                    "last_access": self._last_access.get(k, 0),
                }
                for k, b in self._buckets.items()
            }
