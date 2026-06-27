from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from inmob.standardization.contracts import QuarantineArtifact, RawArtifactMetadata
from inmob.standardization.parsers import ParserError, parse_listing
from inmob.standardization.runner import SilverProcessingRunner
from inmob.standardization.store import SilverSQLiteStore


SOURCES = ("argenprop", "cabaprop", "mudafy", "properati", "remax", "zonaprop")
FIXTURE_RAW_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "raw"


@pytest.mark.parametrize("source", SOURCES)
def test_parse_fixture_raw_sample(source: str) -> None:
    metadata = RawArtifactMetadata.from_file(_sample_metadata_path(source))
    listing = parse_listing(metadata, metadata.payload_path.read_bytes())

    assert listing.source_id == source
    assert listing.source_listing_id
    assert listing.raw_artifact_id == metadata.artifact_id
    assert listing.has_business_anchor()
    assert listing.commercial.price_amount is not None
    assert listing.canonical_url.startswith("https://")


def test_runner_processes_fixture_raw_dir(tmp_path: Path) -> None:
    result = SilverProcessingRunner().run(
        raw_dir=FIXTURE_RAW_DIR,
        db_path=tmp_path / "silver.sqlite",
        quarantine_dir=tmp_path / "quarantine",
    )

    assert result["artifacts"] == len(SOURCES)
    assert result["parsed"] == len(SOURCES)
    assert result["quarantined"] == 0
    assert result["listings_current"] == len(SOURCES)
    assert result["listing_observations"] == len(SOURCES)
    assert result["silver_quarantine"] == 0


def test_sqlite_store_upserts_current_and_keeps_observation(tmp_path: Path) -> None:
    metadata_path = _sample_metadata_path("cabaprop")
    metadata = RawArtifactMetadata.from_file(metadata_path)
    listing = parse_listing(metadata, metadata.payload_path.read_bytes())
    store = SilverSQLiteStore(tmp_path / "silver.sqlite")

    store.initialize()
    store.upsert_listing(listing)
    store.upsert_listing(listing)

    counts = store.counts()
    assert counts["listings_current"] == 1
    assert counts["listing_attributes_current"] > 0
    assert counts["listing_observations"] == 1

    with sqlite3.connect(tmp_path / "silver.sqlite") as conn:
        row = conn.execute(
            """
            SELECT price_amount, currency, source_agency_id, operation_type, surface_exclusive_m2
            FROM listings_current WHERE source_id = ?
            """,
            (listing.source_id,),
        ).fetchone()
        attribute = conn.execute(
            """
            SELECT value_boolean FROM listing_attributes_current
            WHERE source_id = ? AND source_listing_id = ? AND attribute_key = ?
            """,
            (listing.source_id, listing.source_listing_id, "cabaprop.balcony"),
        ).fetchone()
    assert row == (
        listing.commercial.price_amount,
        listing.commercial.currency,
        "fixture-agency",
        "1",
        5.0,
    )
    assert attribute == (1,)


def test_properati_area_value_becomes_total_surface() -> None:
    metadata = RawArtifactMetadata.from_file(_sample_metadata_path("properati"))
    listing = parse_listing(metadata, metadata.payload_path.read_bytes())

    assert listing.surface.total_m2 == 86.0
    assert listing.features.operation_type == "Venta"
    assert listing.features.construction_year == 2026
    assert listing.features.condition == "Excelente"


def test_zonaprop_marker_position_becomes_coordinates_when_script_geo_is_missing() -> None:
    metadata = RawArtifactMetadata.from_file(_sample_metadata_path("zonaprop"))
    payload = metadata.payload_path.read_text(encoding="utf-8").replace(
        '"postingGeolocation": {"geolocation": {"latitude": "-34.592", "longitude": "-58.374"}},',
        '"postingGeolocation": {},',
    )
    payload += '<gmp-advanced-marker position="-34.560893,-58.4429387"></gmp-advanced-marker>'

    listing = parse_listing(metadata, payload.encode("utf-8"))

    assert listing.location.latitude == -34.560893
    assert listing.location.longitude == -58.4429387


def test_quarantine_persists_failure(tmp_path: Path) -> None:
    metadata_path = _sample_metadata_path("cabaprop")
    metadata = RawArtifactMetadata.from_file(metadata_path)
    store = SilverSQLiteStore(tmp_path / "silver.sqlite")
    artifact = QuarantineArtifact(
        raw_artifact_id=metadata.artifact_id,
        source_id=metadata.source_id,
        parser_id="cabaprop_json_v1",
        parser_version="v1",
        failure_category="parser_error",
        diagnostic_detail=str(ParserError("bad payload")),
        retryable=True,
        metadata_path=metadata.metadata_path,
        payload_path=metadata.payload_path,
    )

    store.initialize()
    store.quarantine(artifact)

    assert store.counts()["silver_quarantine"] == 1


def _sample_metadata_path(source: str) -> Path:
    return next((FIXTURE_RAW_DIR / source).glob("*/*_raw_metadata.json"))
