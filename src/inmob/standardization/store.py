"""SQLite persistence for Silver canonical listings."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from inmob.standardization.contracts import CanonicalListing, QuarantineArtifact


LISTING_COLUMNS: dict[str, str] = {
    "source_id": "TEXT NOT NULL",
    "source_listing_id": "TEXT NOT NULL",
    "canonical_url": "TEXT NOT NULL",
    "raw_artifact_id": "TEXT NOT NULL",
    "captured_at": "TEXT NOT NULL",
    "payload_sha256": "TEXT NOT NULL",
    "parser_id": "TEXT NOT NULL",
    "parser_version": "TEXT NOT NULL",
    "title": "TEXT",
    "source_status": "TEXT",
    "source_created_at": "TEXT",
    "source_updated_at": "TEXT",
    "source_advertiser_id": "TEXT",
    "source_agency_id": "TEXT",
    "source_branch_id": "TEXT",
    "source_office_id": "TEXT",
    "source_internal_id": "TEXT",
    "source_posting_code": "TEXT",
    "external_reference": "TEXT",
    "operation_type": "TEXT",
    "property_subtype": "TEXT",
    "price_amount": "REAL",
    "currency": "TEXT",
    "expenses_amount": "REAL",
    "expenses_currency": "TEXT",
    "price_visible": "INTEGER",
    "surface_total_m2": "REAL",
    "surface_covered_m2": "REAL",
    "surface_uncovered_m2": "REAL",
    "surface_semicovered_m2": "REAL",
    "surface_terrace_m2": "REAL",
    "surface_exclusive_m2": "REAL",
    "address": "TEXT",
    "street": "TEXT",
    "neighborhood": "TEXT",
    "city": "TEXT",
    "province": "TEXT",
    "postal_code": "TEXT",
    "commune": "TEXT",
    "map_address": "TEXT",
    "latitude": "REAL",
    "longitude": "REAL",
    "rooms": "INTEGER",
    "bedrooms": "INTEGER",
    "bathrooms": "INTEGER",
    "toilettes": "INTEGER",
    "parking_spaces": "INTEGER",
    "age_years": "INTEGER",
    "property_type": "TEXT",
    "construction_year": "INTEGER",
    "floor_number": "INTEGER",
    "building_floors": "INTEGER",
    "orientation": "TEXT",
    "disposition": "TEXT",
    "brightness": "TEXT",
    "condition": "TEXT",
    "is_new_build": "INTEGER",
    "accepts_credit": "INTEGER",
    "accepts_pets": "INTEGER",
    "professional_use": "INTEGER",
    "commercial_use": "INTEGER",
    "reduced_mobility_access": "INTEGER",
    "financing": "INTEGER",
    "furnished": "INTEGER",
    "seller_name": "TEXT",
    "agency_name": "TEXT",
    "agency_license": "TEXT",
    "office_name": "TEXT",
    "seller_slug": "TEXT",
    "phone": "TEXT",
    "email": "TEXT",
    "whatsapp": "TEXT",
    "whatsapp_contact_enabled": "INTEGER",
    "contact_url": "TEXT",
    "published_at": "TEXT",
    "publication_text": "TEXT",
    "views_count": "INTEGER",
    "features_json": "TEXT NOT NULL",
    "source_specific_json": "TEXT NOT NULL",
    "canonical_json": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
}


class SilverSQLiteStore:
    """Persist current listing state, observations, and quarantines."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)

    def initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings_current (
                    source_id TEXT NOT NULL,
                    source_listing_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    raw_artifact_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    parser_id TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    title TEXT,
                    source_status TEXT,
                    source_created_at TEXT,
                    source_updated_at TEXT,
                    source_advertiser_id TEXT,
                    source_agency_id TEXT,
                    source_branch_id TEXT,
                    source_office_id TEXT,
                    source_internal_id TEXT,
                    source_posting_code TEXT,
                    external_reference TEXT,
                    operation_type TEXT,
                    property_subtype TEXT,
                    price_amount REAL,
                    currency TEXT,
                    expenses_amount REAL,
                    expenses_currency TEXT,
                    price_visible INTEGER,
                    surface_total_m2 REAL,
                    surface_covered_m2 REAL,
                    surface_uncovered_m2 REAL,
                    surface_semicovered_m2 REAL,
                    surface_terrace_m2 REAL,
                    surface_exclusive_m2 REAL,
                    address TEXT,
                    street TEXT,
                    neighborhood TEXT,
                    city TEXT,
                    province TEXT,
                    postal_code TEXT,
                    commune TEXT,
                    map_address TEXT,
                    latitude REAL,
                    longitude REAL,
                    rooms INTEGER,
                    bedrooms INTEGER,
                    bathrooms INTEGER,
                    toilettes INTEGER,
                    parking_spaces INTEGER,
                    age_years INTEGER,
                    property_type TEXT,
                    construction_year INTEGER,
                    floor_number INTEGER,
                    building_floors INTEGER,
                    orientation TEXT,
                    disposition TEXT,
                    brightness TEXT,
                    condition TEXT,
                    is_new_build INTEGER,
                    accepts_credit INTEGER,
                    accepts_pets INTEGER,
                    professional_use INTEGER,
                    commercial_use INTEGER,
                    reduced_mobility_access INTEGER,
                    financing INTEGER,
                    furnished INTEGER,
                    seller_name TEXT,
                    agency_name TEXT,
                    agency_license TEXT,
                    office_name TEXT,
                    seller_slug TEXT,
                    phone TEXT,
                    email TEXT,
                    whatsapp TEXT,
                    whatsapp_contact_enabled INTEGER,
                    contact_url TEXT,
                    published_at TEXT,
                    publication_text TEXT,
                    views_count INTEGER,
                    features_json TEXT NOT NULL,
                    source_specific_json TEXT NOT NULL,
                    canonical_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, source_listing_id)
                );

                CREATE TABLE IF NOT EXISTS listing_attributes_current (
                    source_id TEXT NOT NULL,
                    source_listing_id TEXT NOT NULL,
                    attribute_key TEXT NOT NULL,
                    attribute_label TEXT,
                    attribute_namespace TEXT,
                    value_type TEXT NOT NULL,
                    value_text TEXT,
                    value_number REAL,
                    value_boolean INTEGER,
                    source_path TEXT,
                    raw_artifact_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, source_listing_id, attribute_key)
                );

                CREATE TABLE IF NOT EXISTS listing_observations (
                    raw_artifact_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_listing_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    price_amount REAL,
                    currency TEXT,
                    expenses_amount REAL,
                    views_count INTEGER,
                    canonical_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS silver_quarantine (
                    raw_artifact_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    parser_id TEXT,
                    parser_version TEXT,
                    failure_category TEXT NOT NULL,
                    failure_severity TEXT NOT NULL,
                    diagnostic_detail TEXT NOT NULL,
                    retryable INTEGER NOT NULL,
                    metadata_path TEXT NOT NULL,
                    payload_path TEXT,
                    quarantined_at TEXT NOT NULL,
                    quarantine_json TEXT NOT NULL
                );
                """
            )
            _ensure_columns(conn, "listings_current", LISTING_COLUMNS)

    def upsert_listing(self, listing: CanonicalListing) -> None:
        row = _listing_row(listing)
        with self._connect() as conn:
            columns = tuple(LISTING_COLUMNS)
            placeholders = ", ".join(f":{column}" for column in columns)
            update_assignments = ", ".join(
                f"{column}=excluded.{column}"
                for column in columns
                if column not in {"source_id", "source_listing_id"}
            )
            conn.execute(
                f"""
                INSERT INTO listings_current ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(source_id, source_listing_id) DO UPDATE SET
                    {update_assignments}
                """,
                row,
            )
            conn.execute(
                """
                DELETE FROM listing_attributes_current
                WHERE source_id = ? AND source_listing_id = ?
                """,
                (listing.source_id, listing.source_listing_id),
            )
            conn.executemany(
                """
                INSERT INTO listing_attributes_current (
                    source_id, source_listing_id, attribute_key, attribute_label,
                    attribute_namespace, value_type, value_text, value_number,
                    value_boolean, source_path, raw_artifact_id, updated_at
                )
                VALUES (
                    :source_id, :source_listing_id, :attribute_key, :attribute_label,
                    :attribute_namespace, :value_type, :value_text, :value_number,
                    :value_boolean, :source_path, :raw_artifact_id, :updated_at
                )
                """,
                list(_attribute_rows(listing, row["updated_at"])),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO listing_observations (
                    raw_artifact_id, source_id, source_listing_id, captured_at,
                    payload_sha256, price_amount, currency, expenses_amount,
                    views_count, canonical_json, created_at
                )
                VALUES (
                    :raw_artifact_id, :source_id, :source_listing_id, :captured_at,
                    :payload_sha256, :price_amount, :currency, :expenses_amount,
                    :views_count, :canonical_json, :updated_at
                )
                """,
                row,
            )

    def quarantine(self, artifact: QuarantineArtifact) -> None:
        data = artifact.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO silver_quarantine (
                    raw_artifact_id, source_id, parser_id, parser_version,
                    failure_category, failure_severity, diagnostic_detail, retryable,
                    metadata_path, payload_path, quarantined_at, quarantine_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.raw_artifact_id,
                    artifact.source_id,
                    artifact.parser_id,
                    artifact.parser_version,
                    artifact.failure_category,
                    artifact.failure_severity,
                    artifact.diagnostic_detail,
                    1 if artifact.retryable else 0,
                    str(artifact.metadata_path),
                    str(artifact.payload_path) if artifact.payload_path else None,
                    artifact.quarantined_at.isoformat(),
                    json.dumps(data, sort_keys=True),
                ),
            )

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "listings_current": _count(conn, "listings_current"),
                "listing_attributes_current": _count(conn, "listing_attributes_current"),
                "listing_observations": _count(conn, "listing_observations"),
                "silver_quarantine": _count(conn, "silver_quarantine"),
            }

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)


def _listing_row(listing: CanonicalListing) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    source = listing.source_specific
    return {
        "source_id": listing.source_id,
        "source_listing_id": listing.source_listing_id,
        "canonical_url": listing.canonical_url,
        "raw_artifact_id": listing.raw_artifact_id,
        "captured_at": listing.captured_at.isoformat(),
        "payload_sha256": listing.payload_sha256,
        "parser_id": listing.parser_id,
        "parser_version": listing.parser_version,
        "title": listing.title,
        "source_status": _str_or_none(source.get("source_status")),
        "source_created_at": _str_or_none(source.get("source_created_at")),
        "source_updated_at": _str_or_none(source.get("source_updated_at")),
        "source_advertiser_id": _str_or_none(source.get("source_advertiser_id")),
        "source_agency_id": _str_or_none(source.get("source_agency_id")),
        "source_branch_id": _str_or_none(source.get("source_branch_id")),
        "source_office_id": _str_or_none(source.get("source_office_id")),
        "source_internal_id": _str_or_none(source.get("source_internal_id")),
        "source_posting_code": _str_or_none(source.get("source_posting_code") or source.get("posting_code")),
        "external_reference": _str_or_none(source.get("external_reference")),
        "operation_type": listing.features.operation_type,
        "property_subtype": listing.features.property_subtype,
        "price_amount": listing.commercial.price_amount,
        "currency": listing.commercial.currency,
        "expenses_amount": listing.commercial.expenses_amount,
        "expenses_currency": listing.commercial.expenses_currency,
        "price_visible": _bool_int(listing.commercial.price_visible),
        "surface_total_m2": listing.surface.total_m2,
        "surface_covered_m2": listing.surface.covered_m2,
        "surface_uncovered_m2": listing.surface.uncovered_m2,
        "surface_semicovered_m2": listing.surface.semicovered_m2,
        "surface_terrace_m2": listing.surface.terrace_m2,
        "surface_exclusive_m2": listing.surface.exclusive_m2,
        "address": listing.location.address,
        "street": listing.location.street,
        "neighborhood": listing.location.neighborhood,
        "city": listing.location.city,
        "province": listing.location.province,
        "postal_code": listing.location.postal_code,
        "commune": listing.location.commune,
        "map_address": listing.location.map_address,
        "latitude": listing.location.latitude,
        "longitude": listing.location.longitude,
        "rooms": listing.features.rooms,
        "bedrooms": listing.features.bedrooms,
        "bathrooms": listing.features.bathrooms,
        "toilettes": listing.features.toilettes,
        "parking_spaces": listing.features.parking_spaces,
        "age_years": listing.features.age_years,
        "property_type": listing.features.property_type,
        "construction_year": listing.features.construction_year,
        "floor_number": listing.features.floor_number,
        "building_floors": listing.features.building_floors,
        "orientation": listing.features.orientation,
        "disposition": listing.features.disposition,
        "brightness": listing.features.brightness,
        "condition": listing.features.condition,
        "is_new_build": _bool_int(listing.features.is_new_build),
        "accepts_credit": _bool_int(listing.features.accepts_credit),
        "accepts_pets": _bool_int(listing.features.accepts_pets),
        "professional_use": _bool_int(listing.features.professional_use),
        "commercial_use": _bool_int(listing.features.commercial_use),
        "reduced_mobility_access": _bool_int(listing.features.reduced_mobility_access),
        "financing": _bool_int(listing.features.financing),
        "furnished": _bool_int(listing.features.furnished),
        "seller_name": listing.seller.seller_name,
        "agency_name": listing.seller.agency_name,
        "agency_license": listing.seller.agency_license,
        "office_name": listing.seller.office_name,
        "seller_slug": listing.seller.seller_slug,
        "phone": listing.seller.phone,
        "email": listing.seller.email,
        "whatsapp": listing.seller.whatsapp,
        "whatsapp_contact_enabled": _bool_int(listing.seller.whatsapp_contact_enabled),
        "contact_url": listing.seller.contact_url,
        "published_at": listing.published_at.isoformat() if listing.published_at else None,
        "publication_text": listing.publication_text,
        "views_count": listing.views_count,
        "features_json": json.dumps(listing.features.model_dump(mode="json"), sort_keys=True),
        "source_specific_json": json.dumps(listing.source_specific, sort_keys=True),
        "canonical_json": json.dumps(listing.model_dump(mode="json"), sort_keys=True),
        "updated_at": now,
    }


def _attribute_rows(listing: CanonicalListing, updated_at: str) -> list[dict[str, Any]]:
    rows = []
    attributes: dict[str, Any] = {**listing.features.booleans, **listing.features.attributes}
    for key, value in sorted(attributes.items()):
        row = _attribute_row(listing, key, value, updated_at)
        if row is not None:
            rows.append(row)
    return rows


def _attribute_row(
    listing: CanonicalListing,
    key: str,
    value: Any,
    updated_at: str,
) -> dict[str, Any] | None:
    attribute_key = _attribute_key(listing.source_id, key)
    if value is None or value == "":
        return None
    value_boolean = None
    value_number = None
    value_text = None
    value_type = "text"
    if isinstance(value, bool):
        value_type = "boolean"
        value_boolean = 1 if value else 0
    elif isinstance(value, int | float):
        value_type = "number"
        value_number = float(value)
        value_text = str(value)
    else:
        value_text = str(value)
    namespace = attribute_key.split(".", 1)[0] if "." in attribute_key else listing.source_id
    return {
        "source_id": listing.source_id,
        "source_listing_id": listing.source_listing_id,
        "attribute_key": attribute_key,
        "attribute_label": _attribute_label(key),
        "attribute_namespace": namespace,
        "value_type": value_type,
        "value_text": value_text,
        "value_number": value_number,
        "value_boolean": value_boolean,
        "source_path": key,
        "raw_artifact_id": listing.raw_artifact_id,
        "updated_at": updated_at,
    }


def _attribute_key(source_id: str, key: str) -> str:
    cleaned = str(key)
    if cleaned.startswith(f"{source_id}."):
        return cleaned
    return f"{source_id}.{_slug(cleaned)}"


def _attribute_label(key: str) -> str:
    return str(key).split(".")[-1].replace("_", " ").strip()


def _slug(value: str) -> str:
    text = value.lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown"


def _bool_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _count(conn: sqlite3.Connection, table: str) -> int:
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
    value = cursor.fetchone()[0]
    return int(value)
