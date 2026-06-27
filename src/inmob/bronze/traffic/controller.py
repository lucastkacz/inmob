"""Responsible traffic control for Bronze."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Mapping, Protocol, TypeVar

import httpx
from loguru import logger

from inmob.bronze.contracts import PolitenessProfile, RetryProfile


RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


class StatusResponse(Protocol):
    @property
    def status_code(self) -> int: ...

    @property
    def headers(self) -> dict[str, str] | httpx.Headers: ...


T = TypeVar("T", bound=StatusResponse)

POLITENESS_INFO_THRESHOLD_SECONDS = 0.25


@dataclass(frozen=True, slots=True)
class TrafficSnapshot:
    """Operational traffic metrics collected for one controller."""

    logical_requests: int
    request_attempts: int
    responses_returned: int
    retry_count: int
    transport_error_count: int
    retryable_status_count: int
    politeness_wait_count: int
    politeness_wait_total_seconds: float
    retry_wait_count: int
    retry_wait_total_seconds: float


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
        self._stats_lock = threading.Lock()
        self._logical_requests = 0
        self._request_attempts = 0
        self._responses_returned = 0
        self._retry_count = 0
        self._transport_error_count = 0
        self._retryable_status_count = 0
        self._politeness_wait_count = 0
        self._politeness_wait_total_seconds = 0.0
        self._retry_wait_count = 0
        self._retry_wait_total_seconds = 0.0

    def request(
        self,
        send: Callable[[], T],
        *,
        log_context: Mapping[str, str] | None = None,
    ) -> T:
        """Run one polite HTTP request with retry/backoff behavior."""

        retry = self._profile.retry
        last_transport_error: httpx.TransportError | None = None
        request_logger = logger.bind(**(dict(log_context) if log_context is not None else {}))
        self._record_logical_request()

        for attempt in range(1, retry.max_attempts + 1):
            wait_seconds = self._bucket.wait_for_token()
            self._record_attempt(wait_seconds=wait_seconds)
            if wait_seconds > 0:
                log_method = (
                    request_logger.info
                    if wait_seconds >= POLITENESS_INFO_THRESHOLD_SECONDS
                    else request_logger.debug
                )
                log_method(
                    "Politeness delay before request attempt={} wait_seconds={} "
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
                self._record_transport_error()
                if attempt == retry.max_attempts:
                    request_logger.exception(
                        "Transport error exhausted retry attempts attempt={} max_attempts={}",
                        attempt,
                        retry.max_attempts,
                    )
                    raise
                delay_seconds = self._retry_delay_seconds(retry=retry, attempt=attempt)
                self._record_retry(delay_seconds=delay_seconds)
                request_logger.warning(
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
                self._record_response_returned()
                return response

            self._record_retryable_status()
            if attempt == retry.max_attempts:
                request_logger.warning(
                    "Retryable HTTP status exhausted retry attempts status_code={} attempt={} "
                    "max_attempts={}",
                    response.status_code,
                    attempt,
                    retry.max_attempts,
                )
                self._record_response_returned()
                return response

            retry_after = response.headers.get("retry-after")
            delay_seconds = self._retry_delay_seconds(
                retry=retry,
                attempt=attempt,
                retry_after=retry_after,
            )
            self._record_retry(delay_seconds=delay_seconds)
            request_logger.warning(
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

    def snapshot(self) -> TrafficSnapshot:
        """Return a point-in-time traffic metrics snapshot."""

        with self._stats_lock:
            return TrafficSnapshot(
                logical_requests=self._logical_requests,
                request_attempts=self._request_attempts,
                responses_returned=self._responses_returned,
                retry_count=self._retry_count,
                transport_error_count=self._transport_error_count,
                retryable_status_count=self._retryable_status_count,
                politeness_wait_count=self._politeness_wait_count,
                politeness_wait_total_seconds=round(self._politeness_wait_total_seconds, 3),
                retry_wait_count=self._retry_wait_count,
                retry_wait_total_seconds=round(self._retry_wait_total_seconds, 3),
            )

    def reset_stats(self) -> None:
        """Reset accumulated traffic metrics."""

        with self._stats_lock:
            self._logical_requests = 0
            self._request_attempts = 0
            self._responses_returned = 0
            self._retry_count = 0
            self._transport_error_count = 0
            self._retryable_status_count = 0
            self._politeness_wait_count = 0
            self._politeness_wait_total_seconds = 0.0
            self._retry_wait_count = 0
            self._retry_wait_total_seconds = 0.0

    def _record_logical_request(self) -> None:
        with self._stats_lock:
            self._logical_requests += 1

    def _record_attempt(self, *, wait_seconds: float) -> None:
        with self._stats_lock:
            self._request_attempts += 1
            if wait_seconds > 0:
                self._politeness_wait_count += 1
                self._politeness_wait_total_seconds += wait_seconds

    def _record_response_returned(self) -> None:
        with self._stats_lock:
            self._responses_returned += 1

    def _record_retry(self, *, delay_seconds: float) -> None:
        with self._stats_lock:
            self._retry_count += 1
            self._retry_wait_count += 1
            self._retry_wait_total_seconds += delay_seconds

    def _record_retryable_status(self) -> None:
        with self._stats_lock:
            self._retryable_status_count += 1

    def _record_transport_error(self) -> None:
        with self._stats_lock:
            self._transport_error_count += 1

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
