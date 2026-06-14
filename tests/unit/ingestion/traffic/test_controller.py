import httpx

from inmob.ingestion.contracts import PolitenessProfile, RetryProfile
from inmob.ingestion.traffic import TokenBucket, TrafficController


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_token_bucket_allows_burst_then_waits_for_refill() -> None:
    clock = FakeClock()
    bucket = TokenBucket(
        capacity=2,
        refill_rate_per_second=1,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    bucket.wait_for_token()
    bucket.wait_for_token()
    bucket.wait_for_token()

    assert clock.sleeps == [1.0]


def test_traffic_controller_retries_429_with_full_jitter_backoff() -> None:
    clock = FakeClock()
    profile = PolitenessProfile(
        requests_per_minute=600,
        burst_size=10,
        retry=RetryProfile(
            max_attempts=3,
            initial_delay_seconds=2,
            max_delay_seconds=30,
        ),
    )
    controller = TrafficController(
        profile=profile,
        clock=clock.monotonic,
        sleep=clock.sleep,
        random_uniform=lambda lower, upper: upper,
    )
    responses = [httpx.Response(429), httpx.Response(200)]

    response = controller.request(lambda: responses.pop(0))

    assert response.status_code == 200
    assert clock.sleeps == [2.0]


def test_traffic_controller_honors_retry_after_header() -> None:
    clock = FakeClock()
    profile = PolitenessProfile(
        requests_per_minute=600,
        burst_size=10,
        retry=RetryProfile(max_attempts=2, initial_delay_seconds=1, max_delay_seconds=30),
    )
    controller = TrafficController(
        profile=profile,
        clock=clock.monotonic,
        sleep=clock.sleep,
        random_uniform=lambda lower, upper: upper,
    )
    responses = [httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(200)]

    response = controller.request(lambda: responses.pop(0))

    assert response.status_code == 200
    assert clock.sleeps == [7.0]


def test_traffic_controller_snapshot_tracks_waits_and_retries() -> None:
    clock = FakeClock()
    profile = PolitenessProfile(
        requests_per_minute=60,
        burst_size=1,
        retry=RetryProfile(max_attempts=2, initial_delay_seconds=2, max_delay_seconds=30),
    )
    controller = TrafficController(
        profile=profile,
        clock=clock.monotonic,
        sleep=clock.sleep,
        random_uniform=lambda lower, upper: upper,
    )
    retry_responses = [httpx.Response(429), httpx.Response(200)]

    assert controller.request(lambda: httpx.Response(200)).status_code == 200
    assert controller.request(lambda: retry_responses.pop(0)).status_code == 200

    snapshot = controller.snapshot()

    assert snapshot.logical_requests == 2
    assert snapshot.request_attempts == 3
    assert snapshot.responses_returned == 2
    assert snapshot.retry_count == 1
    assert snapshot.retryable_status_count == 1
    assert snapshot.politeness_wait_count == 1
    assert snapshot.politeness_wait_total_seconds == 1.0
    assert snapshot.retry_wait_count == 1
    assert snapshot.retry_wait_total_seconds == 2.0

    controller.reset_stats()

    reset_snapshot = controller.snapshot()
    assert reset_snapshot.logical_requests == 0
    assert reset_snapshot.request_attempts == 0
