"""Tests for rate limiting."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import unittest

from security.rate_limiter import RateLimiter, TokenBucket


class TestTokenBucket(unittest.TestCase):
    """Tests for token bucket."""

    def test_consume_available(self):
        """Consume when tokens available."""
        bucket = TokenBucket(capacity=5, refill_rate=1)
        self.assertTrue(bucket.consume(1))
        self.assertTrue(bucket.consume(4))

    def test_consume_empty(self):
        """Consume fails when empty."""
        bucket = TokenBucket(capacity=1, refill_rate=0.1)
        self.assertTrue(bucket.consume(1))
        self.assertFalse(bucket.consume(1))

    def test_refill(self):
        """Tokens refill over time."""
        bucket = TokenBucket(capacity=2, refill_rate=10)
        bucket.consume(2)  # Empty the bucket
        time.sleep(0.15)
        self.assertTrue(bucket.consume(1))  # Refilled

    def test_wait_time(self):
        """Wait time calculation."""
        bucket = TokenBucket(capacity=1, refill_rate=1)
        bucket.consume(1)
        wait = bucket.wait_time(1)
        self.assertGreater(wait, 0)

    def test_wait_time_available(self):
        """Zero wait when available."""
        bucket = TokenBucket(capacity=5, refill_rate=1)
        self.assertEqual(bucket.wait_time(1), 0.0)


class TestRateLimiter(unittest.TestCase):
    """Tests for rate limiter."""

    def test_is_allowed(self):
        """Request allowed within limit."""
        rl = RateLimiter(default_capacity=3, default_refill_rate=1)
        self.assertTrue(rl.is_allowed("client1"))
        self.assertTrue(rl.is_allowed("client1"))
        self.assertTrue(rl.is_allowed("client1"))

    def test_is_denied(self):
        """Request denied when exceeded."""
        rl = RateLimiter(default_capacity=2, default_refill_rate=0.1)
        self.assertTrue(rl.is_allowed("client1"))
        self.assertTrue(rl.is_allowed("client1"))
        self.assertFalse(rl.is_allowed("client1"))

    def test_check_returns_retry(self):
        """Check returns retry-after when limited."""
        rl = RateLimiter(default_capacity=1, default_refill_rate=1)
        rl.is_allowed("client1")
        allowed, retry = rl.check("client1")
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)

    def test_independent_keys(self):
        """Different keys have independent buckets."""
        rl = RateLimiter(default_capacity=2, default_refill_rate=1)
        rl.is_allowed("client1")
        rl.is_allowed("client1")
        self.assertTrue(rl.is_allowed("client2"))

    def test_reset(self):
        """Reset clears rate limit."""
        rl = RateLimiter(default_capacity=1, default_refill_rate=0.1)
        rl.is_allowed("client1")
        rl.reset("client1")
        self.assertTrue(rl.is_allowed("client1"))

    def test_status(self):
        """Status returns bucket info."""
        rl = RateLimiter(default_capacity=5, default_refill_rate=1)
        rl.is_allowed("c1")
        status = rl.get_status()
        self.assertIn("c1", status)
        self.assertEqual(status["c1"]["capacity"], 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
