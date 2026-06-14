"""Responsible traffic control for Bronze ingestion."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Protocol, TypeVar

import httpx
from loguru import logger

from inmob.ingestion.contracts import PolitenessProfile, RetryProfile


RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


class StatusResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> dict[str, str] | httpx.Headers: ...


T = TypeVar("T", bound=StatusResponse)



class TokenBucket:
    """Token Bucket rate limiter.

    The bucket allows short bursts up to ``capacity`` and then refills at a
    steady rate. This keeps normal browsing-like bursts possible while still
    enforcing a long-term requests-per-minute limit.
    """

    def __init__(
        self,
        *,
        capacity: int,
        refill_rate_per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be greater than zero")
        if refill_rate_per_second <= 0:
            raise ValueError("refill_rate_per_second must be greater than zero")

        self._capacity = float(capacity)
        self._refill_rate_per_second = refill_rate_per_second
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(capacity)
        self._last_refill_at = clock()
        self._lock = threading.Lock()

    def wait_for_token(self) -> float:
        """Block until one request token is available and return wait seconds."""

        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return 0.0

            missing_tokens = 1 - self._tokens
            wait_seconds = missing_tokens / self._refill_rate_per_second
            self._sleep(wait_seconds)
            self._refill()
            self._tokens = max(0.0, self._tokens - 1)
            return wait_seconds

    def _refill(self) -> None:
        now = self._clock()
        elapsed_seconds = max(0.0, now - self._last_refill_at)
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed_seconds * self._refill_rate_per_second,
        )
        self._last_refill_at = now


class TrafficController:
    """Apply source politeness before and between HTTP attempts."""

    def __init__(
        self,
        *,
        profile: PolitenessProfile,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._profile = profile
        self._sleep = sleep
        self._random_uniform = random_uniform
        self._bucket = TokenBucket(
            capacity=profile.burst_size,
            refill_rate_per_second=profile.requests_per_minute / 60,
            clock=clock,
            sleep=sleep,
        )

    def request(self, send: Callable[[], T]) -> T:
        """Run one polite HTTP request with retry/backoff behavior."""

        retry = self._profile.retry
        last_transport_error: httpx.TransportError | None = None

        for attempt in range(1, retry.max_attempts + 1):
            wait_seconds = self._bucket.wait_for_token()
            if wait_seconds > 0:
                logger.debug(
                    "Politeness delay before request attempt={} delay_seconds={} "
                    "requests_per_minute={} burst_size={}",
                    attempt,
                    round(wait_seconds, 3),
                    self._profile.requests_per_minute,
                    self._profile.burst_size,
                )

            try:
                response = send()
            except httpx.TransportError as exc:
                last_transport_error = exc
                if attempt == retry.max_attempts:
                    logger.exception(
                        "Transport error exhausted retry attempts attempt={} max_attempts={}",
                        attempt,
                        retry.max_attempts,
                    )
                    raise
                delay_seconds = self._retry_delay_seconds(retry=retry, attempt=attempt)
                logger.warning(
                    "Transport error during request; retrying attempt={} max_attempts={} "
                    "delay_seconds={} error_type={}",
                    attempt,
                    retry.max_attempts,
                    round(delay_seconds, 3),
                    type(exc).__name__,
                )
                self._sleep(delay_seconds)
                continue

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response

            if attempt == retry.max_attempts:
                logger.warning(
                    "Retryable HTTP status exhausted retry attempts status_code={} attempt={} "
                    "max_attempts={}",
                    response.status_code,
                    attempt,
                    retry.max_attempts,
                )
                return response

            retry_after = response.headers.get("retry-after")
            delay_seconds = self._retry_delay_seconds(
                retry=retry,
                attempt=attempt,
                retry_after=retry_after,
            )
            logger.warning(
                "Retryable HTTP status received; retrying status_code={} attempt={} "
                "max_attempts={} delay_seconds={} retry_after={}",
                response.status_code,
                attempt,
                retry.max_attempts,
                round(delay_seconds, 3),
                retry_after,
            )
            self._sleep(delay_seconds)

        if last_transport_error is not None:
            raise last_transport_error
        raise RuntimeError("traffic controller exhausted attempts without a response")

    def _retry_delay_seconds(
        self,
        *,
        retry: RetryProfile,
        attempt: int,
        retry_after: str | None = None,
    ) -> float:
        parsed_retry_after = _parse_retry_after_seconds(retry_after)
        if parsed_retry_after is not None:
            return min(retry.max_delay_seconds, parsed_retry_after)

        exponential_cap = min(
            retry.max_delay_seconds,
            retry.initial_delay_seconds * (2 ** (attempt - 1)),
        )
        return self._random_uniform(0, exponential_cap)


def _parse_retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None

    stripped = value.strip()
    if not stripped:
        return None

    if stripped.isdigit():
        return float(stripped)

    try:
        retry_at = parsedate_to_datetime(stripped)
    except (TypeError, ValueError):
        return None

    return max(0.0, retry_at.timestamp() - time.time())
