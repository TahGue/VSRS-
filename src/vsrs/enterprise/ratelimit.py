"""Rate limiting for API endpoints.

Provides token bucket and sliding window rate limiters for
controlling request rates per user or API key.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("enterprise.ratelimit")


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        requests_per_minute: Maximum requests per minute.
        requests_per_hour: Maximum requests per hour.
        burst_size: Maximum burst size (token bucket).
    """

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "requests_per_hour": self.requests_per_hour,
            "burst_size": self.burst_size,
        }


@dataclass
class RateLimitResult:
    """Result of a rate limit check.

    Attributes:
        allowed: Whether the request is allowed.
        remaining: Remaining requests in the current window.
        reset_at: Unix timestamp when the limit resets.
        retry_after: Seconds to wait before retrying (if denied).
    """

    allowed: bool = True
    remaining: int = 0
    reset_at: float = 0.0
    retry_after: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "reset_at": self.reset_at,
            "retry_after": self.retry_after,
        }


class RateLimiter:
    """Sliding window rate limiter.

    Tracks request timestamps per identifier (user ID, API key, IP)
    and enforces rate limits using a sliding window algorithm.

    Args:
        config: Rate limit configuration.
    """

    def __init__(self, config: RateLimitConfig | None = None) -> None:
        self.config = config or RateLimitConfig()
        self._minute_requests: dict[str, list[float]] = {}
        self._hour_requests: dict[str, list[float]] = {}
        self._burst_tokens: dict[str, float] = {}

    def check(self, identifier: str) -> RateLimitResult:
        """Check if a request is allowed under the rate limit.

        Args:
            identifier: Unique identifier (user ID, API key, IP).

        Returns:
            RateLimitResult indicating whether the request is allowed.
        """
        now = time.time()

        # Check burst (token bucket)
        burst_result = self._check_burst(identifier, now)
        if not burst_result.allowed:
            return burst_result

        # Check per-minute limit
        minute_result = self._check_window(
            identifier,
            now,
            self._minute_requests,
            window_seconds=60,
            max_requests=self.config.requests_per_minute,
        )
        if not minute_result.allowed:
            return minute_result

        # Check per-hour limit
        hour_result = self._check_window(
            identifier,
            now,
            self._hour_requests,
            window_seconds=3600,
            max_requests=self.config.requests_per_hour,
        )
        if not hour_result.allowed:
            return hour_result

        # All checks passed — record the request
        self._record_request(identifier, now)

        remaining = min(
            burst_result.remaining,
            minute_result.remaining,
            hour_result.remaining,
        )

        return RateLimitResult(
            allowed=True,
            remaining=remaining,
            reset_at=now + 60,
            retry_after=0.0,
        )

    def _check_burst(self, identifier: str, now: float) -> RateLimitResult:
        """Check burst limit using token bucket."""
        tokens = self._burst_tokens.get(identifier, float(self.config.burst_size))

        if tokens >= 1:
            self._burst_tokens[identifier] = tokens - 1
            return RateLimitResult(
                allowed=True,
                remaining=int(tokens),
                reset_at=now + 1,
            )
        else:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=now + 1,
                retry_after=1.0,
            )

    def _check_window(
        self,
        identifier: str,
        now: float,
        store: dict[str, list[float]],
        window_seconds: int,
        max_requests: int,
    ) -> RateLimitResult:
        """Check sliding window rate limit."""
        requests = store.get(identifier, [])
        cutoff = now - window_seconds
        recent = [t for t in requests if t > cutoff]

        if len(recent) >= max_requests:
            oldest = recent[0] if recent else now
            reset_at = oldest + window_seconds
            retry_after = max(0.0, reset_at - now)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
            )

        return RateLimitResult(
            allowed=True,
            remaining=max_requests - len(recent),
            reset_at=now + window_seconds,
        )

    def _record_request(self, identifier: str, now: float) -> None:
        """Record a request timestamp."""
        # Record in minute window
        minute_reqs = self._minute_requests.get(identifier, [])
        minute_reqs.append(now)
        cutoff = now - 60
        self._minute_requests[identifier] = [t for t in minute_reqs if t > cutoff]

        # Record in hour window
        hour_reqs = self._hour_requests.get(identifier, [])
        hour_reqs.append(now)
        cutoff = now - 3600
        self._hour_requests[identifier] = [t for t in hour_reqs if t > cutoff]

    def reset(self, identifier: str | None = None) -> None:
        """Reset rate limit state.

        Args:
            identifier: Reset for a specific identifier, or all if None.
        """
        if identifier is None:
            self._minute_requests.clear()
            self._hour_requests.clear()
            self._burst_tokens.clear()
        else:
            self._minute_requests.pop(identifier, None)
            self._hour_requests.pop(identifier, None)
            self._burst_tokens.pop(identifier, None)

    def get_usage(self, identifier: str) -> dict[str, Any]:
        """Get current usage stats for an identifier.

        Returns:
            Dict with minute, hour, and burst usage.
        """
        now = time.time()
        minute_reqs = [t for t in self._minute_requests.get(identifier, []) if t > now - 60]
        hour_reqs = [t for t in self._hour_requests.get(identifier, []) if t > now - 3600]
        burst = self._burst_tokens.get(identifier, float(self.config.burst_size))

        return {
            "minute_used": len(minute_reqs),
            "minute_limit": self.config.requests_per_minute,
            "hour_used": len(hour_reqs),
            "hour_limit": self.config.requests_per_hour,
            "burst_remaining": int(burst),
            "burst_limit": self.config.burst_size,
        }
