import json
from collections import OrderedDict
from pathlib import Path
from shutil import rmtree

from inmob.ingestion.contracts import (
    IngestionRunContext,
    IngestionTarget,
    PolitenessProfile,
    RetryProfile,
)
from inmob.ingestion.raw_store import FileSystemRawArtifactStore
from inmob.ingestion.sources import ProperatiSearchCriteria, ProperatiSource
from inmob.ingestion.traffic import TrafficController


EXPORT_ROOT = Path("TOMAS_ACA_TENES_LOS_RAW_DE_PROPERATI")
PAGES = (1,)
PAGE_SIZE = 30
BULK_POLITENESS = PolitenessProfile(
    requests_per_minute=20,
    burst_size=2,
    retry=RetryProfile(
        max_attempts=3,
        initial_delay_seconds=1.0,
        max_delay_seconds=20.0,
    ),
)


def test_properati_bulk_caba_buy_first_page_raw_export() -> None:
    criteria = ProperatiSearchCriteria(
        operation="venta",
        location="capital-federal",
        property_type="departamento",
        sort="published_on_desc",
        label="caba-buy",
    )
    search_targets = ProperatiSource.search_targets(criteria=criteria, pages=PAGES)
    context = IngestionRunContext(run_id="TOMAS_ACA_TENES_LOS_RAW_DE_PROPERATI")
    store = FileSystemRawArtifactStore(EXPORT_ROOT)
    traffic = TrafficController(profile=BULK_POLITENESS)
    discovered_by_uri: OrderedDict[str, IngestionTarget] = OrderedDict()
    discovered_listing_count = 0

    if EXPORT_ROOT.exists():
        rmtree(EXPORT_ROOT)

    print(f"Export root: {EXPORT_ROOT.resolve()}")
    print(f"Search pages: {PAGES}")
    print(f"Expected theoretical listings: {len(PAGES) * PAGE_SIZE}")

    with ProperatiSource(targets=search_targets, traffic_controller=traffic) as search_source:
        for search_request in search_source.plan_requests(context):
            search_response = search_source.fetch(search_request)
            page_listing_targets = search_source.discover_listing_targets(search_response.payload)
            search_target = search_request.target

            print(f"Search page {search_target.metadata['page']} URL: {search_target.uri}")
            print(f"Search page {search_target.metadata['page']} status: {search_response.status_code}")
            print(f"Search page {search_target.metadata['page']} raw bytes: {len(search_response.payload)}")
            print(
                f"Search page {search_target.metadata['page']} discovered listings: "
                f"{len(page_listing_targets)}"
            )

            assert search_response.status_code == 200
            assert search_response.media_type == "text/html"
            assert len(page_listing_targets) >= 20
            discovered_listing_count += len(page_listing_targets)

            for listing_target in page_listing_targets:
                discovered_by_uri.setdefault(listing_target.uri, listing_target)

    # Slice listing targets to 20 for efficient export testing
    listing_targets = tuple(discovered_by_uri.values())[:20]
    print(f"Total listing page slots discovered: {discovered_listing_count}")
    print(f"Unique listing HTML links discovered (sliced for testing): {len(listing_targets)}")

    assert discovered_listing_count >= 20
    assert len(listing_targets) == 20

    artifacts = []
    successful_listing_html_count = 0
    anomalous_listing_responses = []

    with ProperatiSource(targets=listing_targets, traffic_controller=traffic) as listing_source:
        for index, listing_request in enumerate(listing_source.plan_requests(context), start=1):
            listing_response = listing_source.fetch(listing_request)
            listing_target = listing_request.target
            artifact = store.persist(context=context, response=listing_response)
            artifacts.append(artifact)
            is_listing_html = _looks_like_listing_html(
                payload=listing_response.payload,
                status_code=listing_response.status_code,
                media_type=listing_response.media_type,
                target_metadata=listing_target.metadata,
            )
            if is_listing_html:
                successful_listing_html_count += 1
            else:
                anomalous_listing_responses.append(
                    (
                        index,
                        listing_response.status_code,
                        listing_target.metadata["listing_id"],
                        artifact.payload_path,
                    )
                )

            print(
                f"[{index}/{len(listing_targets)}] "
                f"{listing_response.status_code} "
                f"{listing_target.metadata['listing_id']} "
                f"{'listing-html' if is_listing_html else 'anomaly'} "
                f"{len(listing_response.payload)} bytes -> {artifact.payload_path}"
            )

            assert artifact.payload_path.exists()
            assert artifact.metadata_path.exists()
            assert artifact.payload_path.suffix == ".html"

    print(f"Successful listing HTML payloads: {successful_listing_html_count}")
    print(f"Anomalous listing responses: {len(anomalous_listing_responses)}")
    for index, status_code, listing_id, payload_path in anomalous_listing_responses:
        print(f"Anomaly [{index}] status={status_code} listing_id={listing_id} path={payload_path}")

    print(f"Exported raw listing files: {len(artifacts)}")
    print(f"Exported metadata files: {len(artifacts)}")
    print(f"Open this folder: {EXPORT_ROOT.resolve()}")

    assert len(artifacts) == len(listing_targets)
    assert successful_listing_html_count == len(listing_targets)
    assert not anomalous_listing_responses


def _looks_like_listing_html(
    *,
    payload: bytes,
    status_code: int,
    media_type: str | None,
    target_metadata: dict[str, str],
) -> bool:
    if status_code != 200:
        return False
    if media_type != "text/html":
        return False
    if len(payload) < 20_000:
        return False
    if b"listing-price" not in payload:
        return False
    return target_metadata["listing_id"].encode() in payload
