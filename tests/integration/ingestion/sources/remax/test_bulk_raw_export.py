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
from inmob.ingestion.sources import RemaxSearchCriteria, RemaxSource
from inmob.ingestion.traffic import TrafficController


CAPITAL_FEDERAL_LOCATION_FILTER = "in:CF@<b>Capital</b> <b>F</b>ederal::::::"
EXPORT_ROOT = Path("TOMAS_ACA_TENES_LOS_RAW_DE_REMAX")
PAGES = (0,)
PAGE_SIZE = 24
BULK_POLITENESS = PolitenessProfile(
    requests_per_minute=10,
    burst_size=1,
    retry=RetryProfile(
        max_attempts=4,
        initial_delay_seconds=2.0,
        max_delay_seconds=45.0,
    ),
)


def test_remax_bulk_capital_federal_first_three_pages_raw_export() -> None:
    criteria = RemaxSearchCriteria(
        page_size=PAGE_SIZE,
        operation_ids=(1,),
        sort="-createdAt",
        filters=(("locations", CAPITAL_FEDERAL_LOCATION_FILTER),),
        landing_path="comprar-propiedades",
        filter_count=0,
        view_mode="listViewMode",
        label="capital-federal-buy",
    )
    search_targets = RemaxSource.api_search_targets(criteria=criteria, pages=PAGES)
    context = IngestionRunContext(run_id="TOMAS_ACA_TENES_LOS_RAW_DE_REMAX")
    store = FileSystemRawArtifactStore(EXPORT_ROOT)
    traffic = TrafficController(profile=BULK_POLITENESS)
    discovered_by_uri: OrderedDict[str, IngestionTarget] = OrderedDict()

    if EXPORT_ROOT.exists():
        rmtree(EXPORT_ROOT)

    print(f"Export root: {EXPORT_ROOT.resolve()}")
    print(f"Search pages: {PAGES}")
    print(f"Expected theoretical listings: {len(PAGES) * PAGE_SIZE}")
    print(
        "Traffic policy: "
        f"{BULK_POLITENESS.requests_per_minute} requests/minute, "
        f"burst {BULK_POLITENESS.burst_size}, "
        f"{BULK_POLITENESS.retry.max_attempts} max attempts"
    )

    with RemaxSource(targets=search_targets, traffic_controller=traffic) as search_source:
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
            assert page_listing_targets

            for listing_target in page_listing_targets:
                discovered_by_uri.setdefault(listing_target.uri, listing_target)

    listing_targets = tuple(discovered_by_uri.values())
    print(f"Unique listing links discovered: {len(listing_targets)}")

    assert len(listing_targets) == len(PAGES) * PAGE_SIZE

    artifacts = []
    successful_listing_html_count = 0
    anomalous_listing_responses = []

    with RemaxSource(targets=listing_targets, traffic_controller=traffic) as listing_source:
        for index, listing_request in enumerate(listing_source.plan_requests(context), start=1):
            listing_response = listing_source.fetch(listing_request)
            listing_target = listing_request.target
            artifact = store.persist(context=context, response=listing_response)
            artifacts.append(artifact)
            is_listing_html = _looks_like_listing_html(
                slug=listing_target.metadata["slug"],
                payload=listing_response.payload,
                status_code=listing_response.status_code,
            )
            if is_listing_html:
                successful_listing_html_count += 1
            else:
                anomalous_listing_responses.append(
                    (
                        index,
                        listing_response.status_code,
                        listing_target.metadata["slug"],
                        artifact.payload_path,
                    )
                )

            print(
                f"[{index}/{len(listing_targets)}] "
                f"{listing_response.status_code} "
                f"{listing_target.metadata['slug']} "
                f"{'listing-html' if is_listing_html else 'anomaly'} "
                f"{len(listing_response.payload)} bytes -> {artifact.payload_path}"
            )

            assert artifact.payload_path.exists()
            assert artifact.metadata_path.exists()

    print(f"Successful listing HTML payloads: {successful_listing_html_count}")
    print(f"Anomalous listing responses: {len(anomalous_listing_responses)}")
    for index, status_code, slug, payload_path in anomalous_listing_responses:
        print(f"Anomaly [{index}] status={status_code} slug={slug} path={payload_path}")

    print(f"Exported raw listing files: {len(artifacts)}")
    print(f"Exported metadata files: {len(artifacts)}")
    print(f"Open this folder: {EXPORT_ROOT.resolve()}")

    assert len(artifacts) == len(listing_targets)
    assert successful_listing_html_count > 0


def _looks_like_listing_html(*, slug: str, payload: bytes, status_code: int) -> bool:
    if status_code != 200:
        return False
    if len(payload) < 100_000:
        return False
    return slug.encode() in payload
