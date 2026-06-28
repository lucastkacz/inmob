"""Bronze layer contracts.

The contracts in this module deliberately model acquisition facts only. They
must not contain real estate semantics such as price, address, rooms, area, or
currency. Those concepts belong to Silver and later layers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator


class HttpMethod(StrEnum):
    """Transport method for a raw Bronze request."""

    GET = "GET"
    POST = "POST"


class TargetKind(StrEnum):
    """Acquisition-level target category."""

    SEARCH_RESULTS = "search_results"
    LISTING_DETAIL = "listing_detail"
    FEED = "feed"
    OTHER = "other"


class RetryProfile(BaseModel):
    """Abstract retry policy reference for polite traffic management."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = "exponential-backoff-full-jitter"
    max_attempts: PositiveInt = 3
    initial_delay_seconds: float = Field(default=1.0, gt=0)
    max_delay_seconds: float = Field(default=30.0, gt=0)


class PolitenessProfile(BaseModel):
    """Source-level rate and retry policy."""

    model_config = ConfigDict(frozen=True)

    requests_per_minute: PositiveInt
    burst_size: PositiveInt
    retry: RetryProfile = Field(default_factory=RetryProfile)


class SourceDefinition(BaseModel):
    """Stable source identity used by the Bronze layer."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(min_length=1)
    homepage_url: str = Field(min_length=1)
    allowed_domains: tuple[str, ...] = Field(min_length=1)
    notes: str | None = None

    @field_validator("homepage_url")
    @classmethod
    def homepage_url_must_be_http(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("allowed_domains")
    @classmethod
    def allowed_domains_must_be_normalized(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(domain.strip().lower() for domain in value)
        if any(not domain for domain in normalized):
            raise ValueError("allowed_domains cannot contain blank values")
        return normalized


class BronzeRunContext(BaseModel):
    """Context for one Bronze run."""

    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    labels: dict[str, str] = Field(default_factory=dict)


class BronzeTarget(BaseModel):
    """A source-local target to acquire as raw payload."""

    model_config = ConfigDict(frozen=True)

    target_id: str = Field(min_length=1)
    kind: TargetKind
    uri: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("uri")
    @classmethod
    def uri_must_be_http(cls, value: str) -> str:
        return _validate_http_url(value)


class BronzeRequest(BaseModel):
    """Concrete acquisition request planned by a source adapter."""

    model_config = ConfigDict(frozen=True)

    source_id: str = Field(min_length=1)
    target: BronzeTarget
    method: HttpMethod = HttpMethod.GET
    headers: dict[str, str] = Field(default_factory=dict)
    query_params: dict[str, str] = Field(default_factory=dict)
    body: bytes | None = None


class BronzeResponse(BaseModel):
    """Raw response captured from an external source."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    request: BronzeRequest
    status_code: int = Field(ge=100, le=599)
    final_uri: str = Field(min_length=1)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    media_type: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    capture_metadata: dict[str, str] = Field(default_factory=dict)
    payload: bytes

    @field_validator("final_uri")
    @classmethod
    def final_uri_must_be_http(cls, value: str) -> str:
        return _validate_http_url(value)


class RawArtifact(BaseModel):
    """Persisted Bronze artifact metadata.

    The payload itself is stored beside this metadata by a Bronze artifact store.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    artifact_type: Literal["raw_artifact"] = "raw_artifact"
    artifact_id: str = Field(min_length=1)
    artifact_origin: Literal["fetched", "derived"] = "fetched"
    parent_artifact_id: str | None = None
    run_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_kind: TargetKind
    requested_uri: str = Field(min_length=1)
    final_uri: str = Field(min_length=1)
    captured_at: datetime
    status_code: int = Field(ge=100, le=599)
    media_type: str | None
    payload_sha256: str = Field(min_length=64, max_length=64)
    payload_size_bytes: int = Field(ge=0)
    payload_path: Path
    metadata_path: Path
    headers: dict[str, str] = Field(default_factory=dict)
    target_metadata: dict[str, str] = Field(default_factory=dict)
    capture_metadata: dict[str, str] = Field(default_factory=dict)

    def to_json_ready_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return self.model_dump(mode="json")


def _validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("value must be an absolute HTTP(S) URL")
    return value
