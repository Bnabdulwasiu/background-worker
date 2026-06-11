"""
Token Bucket Rate Limiter for per-job-type throughput control.

How the Token Bucket algorithm works:
--------------------------------------
Each job type gets its own "bucket" which:
  1. Has a maximum capacity (burst_size) of tokens.
  2. Refills at a fixed rate (tokens_per_second).
  3. Each job execution consumes 1 token.
  4. If the bucket is empty, the job is rate-limited and deferred.

Example (5 jobs/minute with burst of 8):
  - At capacity: run up to 8 jobs immediately (burst)
  - Sustained rate: 1 token added every 12 seconds → 5/min throughput
  - At t=0:  bucket=8 → job runs, bucket=7
  - At t=12: bucket=8 (refill tick) → job runs, bucket=7
  - If 10 arrive at once: first 8 run, remaining 2 are deferred

This is the same algorithm used by AWS API Gateway, Stripe, and GitHub APIs.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TokenBucket:
    """
    A single token bucket for one job type.

    Args:
        tokens_per_second: Refill rate. e.g. 5/60 = 5 tokens per minute.
        burst_size: Maximum bucket capacity. Allows short bursts above sustained rate.
    """
    tokens_per_second: float
    burst_size: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        # Start full — first burst of jobs can proceed immediately
        self._tokens = self.burst_size
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * self.tokens_per_second
        self._tokens = min(self.burst_size, self._tokens + new_tokens)
        self._last_refill = now

    def consume(self) -> bool:
        """
        Attempt to consume 1 token (run one job).

        Returns:
            True  → token consumed, job may proceed.
            False → bucket empty, job should be deferred.
        """
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    @property
    def tokens_available(self) -> float:
        """Current token level (after refill), for logging/metrics."""
        self._refill()
        return self._tokens

    @property
    def seconds_until_next_token(self) -> float:
        """How many seconds until at least 1 token is available."""
        self._refill()
        if self._tokens >= 1.0:
            return 0.0
        deficit = 1.0 - self._tokens
        return deficit / self.tokens_per_second


class JobRateLimiter:
    """
    Registry of per-job-type Token Buckets.

    Usage:
        limiter = JobRateLimiter(limits={
            "send_email":      (5, 60),   # 5/min, burst of 5
            "upload_file":     (2, 30),   # 2 per 30s, burst of 2
            "generate_report": (10, 60),  # 10/min, burst of 10
        })

        if limiter.consume("send_email"):
            # proceed
        else:
            defer_seconds = limiter.seconds_until_token("send_email")
            # defer the job by defer_seconds
    """

    def __init__(self, limits: dict[str, tuple[int, int]]) -> None:
        """
        Args:
            limits: Map of job_type → (max_jobs, window_seconds).
                    e.g. {"send_email": (5, 60)} = 5 emails per 60 seconds.
        """
        self._buckets: dict[str, TokenBucket] = {}
        for job_type, (max_jobs, window_seconds) in limits.items():
            tokens_per_second = max_jobs / window_seconds
            # Burst size equals the sustained rate limit — allows a batch up-front
            self._buckets[job_type] = TokenBucket(
                tokens_per_second=tokens_per_second,
                burst_size=float(max_jobs),
            )
            logger.info(
                "Rate limit configured",
                extra={
                    "job_type": job_type,
                    "max_jobs": max_jobs,
                    "window_seconds": window_seconds,
                    "tokens_per_second": round(tokens_per_second, 4),
                    "event": "rate_limit_configured",
                },
            )

    def consume(self, job_type: str) -> bool:
        """
        Try to consume a token for the given job type.

        If no rate limit is configured for this type, always returns True
        (unlimited throughput for unconfigured types).

        Returns:
            True → proceed with the job.
            False → job is rate-limited, defer it.
        """
        bucket = self._buckets.get(job_type)
        if bucket is None:
            return True  # No limit configured — always allow
        return bucket.consume()

    def seconds_until_token(self, job_type: str) -> float:
        """
        Returns how many seconds to wait before this job type can run again.
        Returns 0.0 if the job type is not rate-limited.
        """
        bucket = self._buckets.get(job_type)
        if bucket is None:
            return 0.0
        return bucket.seconds_until_next_token

    def tokens_available(self, job_type: str) -> Optional[float]:
        """Returns current token count for a job type, or None if unlimited."""
        bucket = self._buckets.get(job_type)
        if bucket is None:
            return None
        return round(bucket.tokens_available, 2)
