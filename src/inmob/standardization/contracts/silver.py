"""Silver layer contracts for canonical real estate listings."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CANONICAL_CONTRACT_VERSION = "silver.canonical_listing.v1"


class RawArtifactMetadata(BaseModel):
    """Bronze metadata as consumed by Silver."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    artifact_id: str
    run_id: str
    source_id: str
    target_id: str
    target_kind: str
    requested_uri: str
    final_uri: str
    captured_at: datetime
    status_code: int
    media_type: str | None
    payload_sha256: str
    payload_size_bytes: int
    payload_path: Path
    metadata_path: Path
    headers: dict[str, str] = Field(default_factory=dict)
    target_metadata: dict[str, str] = Field(default_factory=dict)
    capture_metadata: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> RawArtifactMetadata:
        data = cls.model_validate_json(path.read_text(encoding="utf-8"))
        payload_path = data.payload_path
        if not payload_path.is_absolute():
            payload_path = path.parent / payload_path.name
        return data.model_copy(update={"metadata_path": path, "payload_path": payload_path})


class CommercialTerms(BaseModel):
    model_config = ConfigDict(frozen=True)

    price_amount: float | None = None
    currency: str | None = None
    expenses_amount: float | None = None
    expenses_currency: str | None = None
    price_visible: bool | None = None


class Surface(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_m2: float | None = None
    covered_m2: float | None = None
    uncovered_m2: float | None = None
    semicovered_m2: float | None = None
    terrace_m2: float | None = None
    exclusive_m2: float | None = None


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str | None = None
    street: str | None = None
    neighborhood: str | None = None
    city: str | None = None
    province: str | None = None
    postal_code: str | None = None
    commune: str | None = None
    map_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SellerContact(BaseModel):
    model_config = ConfigDict(frozen=True)

    seller_name: str | None = None
    agency_name: str | None = None
    agency_license: str | None = None
    office_name: str | None = None
    seller_slug: str | None = None
    phone: str | None = None
    email: str | None = None
    whatsapp: str | None = None
    whatsapp_contact_enabled: bool | None = None
    contact_url: str | None = None


class FeatureSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    rooms: int | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    toilettes: int | None = None
    parking_spaces: int | None = None
    age_years: int | None = None
    property_type: str | None = None
    property_subtype: str | None = None
    operation_type: str | None = None
    construction_year: int | None = None
    floor_number: int | None = None
    building_floors: int | None = None
    orientation: str | None = None
    disposition: str | None = None
    brightness: str | None = None
    condition: str | None = None
    is_new_build: bool | None = None
    accepts_credit: bool | None = None
    accepts_pets: bool | None = None
    professional_use: bool | None = None
    commercial_use: bool | None = None
    reduced_mobility_access: bool | None = None
    financing: bool | None = None
    furnished: bool | None = None
    booleans: dict[str, bool] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    raw_features: dict[str, Any] = Field(default_factory=dict)


class CanonicalListing(BaseModel):
    """Source-agnostic listing shape produced by Silver."""

    model_config = ConfigDict(frozen=True)

    artifact_type: Literal["canonical_listing"] = "canonical_listing"
    canonical_contract_version: str = CANONICAL_CONTRACT_VERSION
    source_id: str
    source_listing_id: str
    canonical_url: str
    raw_artifact_id: str
    captured_at: datetime
    payload_sha256: str
    parser_id: str
    parser_version: str
    title: str | None = None
    commercial: CommercialTerms = Field(default_factory=CommercialTerms)
    surface: Surface = Field(default_factory=Surface)
    location: Location = Field(default_factory=Location)
    seller: SellerContact = Field(default_factory=SellerContact)
    features: FeatureSet = Field(default_factory=FeatureSet)
    published_at: datetime | None = None
    publication_text: str | None = None
    views_count: int | None = None
    source_specific: dict[str, Any] = Field(default_factory=dict)
    validation_status: Literal["accepted"] = "accepted"
    validation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def has_business_anchor(self) -> bool:
        has_price = self.commercial.price_amount is not None
        has_surface = any(
            value is not None
            for value in (
                self.surface.total_m2,
                self.surface.covered_m2,
                self.surface.uncovered_m2,
                self.surface.semicovered_m2,
                self.surface.terrace_m2,
                self.surface.exclusive_m2,
            )
        )
        has_location = any(
            value is not None
            for value in (
                self.location.address,
                self.location.street,
                self.location.neighborhood,
                self.location.city,
                self.location.latitude,
                self.location.longitude,
            )
        )
        return has_price or has_surface or has_location


class ListingObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_type: Literal["listing_observation"] = "listing_observation"
    raw_artifact_id: str
    source_id: str
    source_listing_id: str
    captured_at: datetime
    canonical_listing: CanonicalListing
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_type: Literal["validation_result"] = "validation_result"
    raw_artifact_id: str
    source_id: str
    status: Literal["accepted", "rejected"]
    severity: Literal["info", "warning", "error"]
    failed_rule_ids: tuple[str, ...] = ()
    diagnostic_message: str
    validation_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QuarantineArtifact(BaseModel):
    model_config = ConfigDict(frozen=True)

    artifact_type: Literal["quarantine_artifact"] = "quarantine_artifact"
    raw_artifact_id: str
    source_id: str
    parser_id: str | None
    parser_version: str | None
    failure_category: str
    failure_severity: Literal["warning", "error"] = "error"
    diagnostic_detail: str
    retryable: bool
    metadata_path: Path
    payload_path: Path | None = None
    quarantined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
