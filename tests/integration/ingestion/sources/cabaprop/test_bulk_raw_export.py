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
from inmob.ingestion.sources import CabapropSearchCriteria, CabapropSource
from inmob.ingestion.traffic import TrafficController


BELGRANO_BARRIO_ID = 14
EXPORT_ROOT = Path("TOMAS_ACA_TENES_LOS_RAW_DE_CABAPROP")
PAGES = (1,)
PAGE_SIZE = 12
BULK_POLITENESS = PolitenessProfile(
    requests_per_minute=20,
    burst_size=2,
    retry=RetryProfile(
        max_attempts=3,
        initial_delay_seconds=1.0,
        max_delay_seconds=20.0,
    ),
)


def test_cabaprop_bulk_belgrano_buy_first_page_raw_export() -> None:
    criteria = CabapropSearchCriteria(
        operation="comprar",
        barrios=(BELGRANO_BARRIO_ID,),
        location_slug="belgrano",
        page_size=PAGE_SIZE,
        label="belgrano-buy",
    )
    search_targets = CabapropSource.api_search_targets(criteria=criteria, pages=PAGES)
    context = IngestionRunContext(run_id="TOMAS_ACA_TENES_LOS_RAW_DE_CABAPROP")
    store = FileSystemRawArtifactStore(EXPORT_ROOT)
    traffic = TrafficController(profile=BULK_POLITENESS)
    discovered_api_by_uri: OrderedDict[str, IngestionTarget] = OrderedDict()
    discovered_listing_count = 0

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

    with CabapropSource(targets=search_targets, traffic_controller=traffic) as search_source:
        for search_request in search_source.plan_requests(context):
            search_response = search_source.fetch(search_request)
            page_listing_targets = search_source.discover_listing_targets(search_response.payload)
            search_target = search_request.target

            print(f"Search page {search_target.metadata['page']} URL: {search_target.uri}")
            print(f"Public page {search_target.metadata['page']} URL: {search_target.metadata['public_url']}")
            print(f"Search page {search_target.metadata['page']} status: {search_response.status_code}")
            print(f"Search page {search_target.metadata['page']} raw bytes: {len(search_response.payload)}")
            print(
                f"Search page {search_target.metadata['page']} discovered listings: "
                f"{len(page_listing_targets)}"
            )

            assert search_response.status_code == 201
            assert search_response.media_type == "application/json"
            assert search_target.metadata["public_url"].endswith(
                "/propiedades/comprar-belgrano?pagina=1"
            )
            assert len(page_listing_targets) == PAGE_SIZE
            discovered_listing_count += len(page_listing_targets)

            for listing_target in page_listing_targets:
                discovered_api_by_uri.setdefault(listing_target.uri, listing_target)

    listing_targets = tuple(discovered_api_by_uri.values())
    print(f"Total listing page slots discovered: {discovered_listing_count}")
    print(f"Unique listing API links discovered: {len(listing_targets)}")

    assert discovered_listing_count == len(PAGES) * PAGE_SIZE
    assert len(listing_targets) == len(PAGES) * PAGE_SIZE

    artifacts = []
    successful_listing_json_count = 0
    anomalous_listing_responses = []

    with CabapropSource(targets=listing_targets, traffic_controller=traffic) as listing_source:
        for index, listing_request in enumerate(listing_source.plan_requests(context), start=1):
            listing_response = listing_source.fetch(listing_request)
            listing_target = listing_request.target
            artifact = store.persist(context=context, response=listing_response)
            artifacts.append(artifact)
            is_listing_json = _looks_like_listing_json(
                payload=listing_response.payload,
                status_code=listing_response.status_code,
                media_type=listing_response.media_type,
                target_metadata=listing_target.metadata,
            )
            if is_listing_json:
                successful_listing_json_count += 1
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
                f"{'listing-json' if is_listing_json else 'anomaly'} "
                f"{len(listing_response.payload)} bytes -> {artifact.payload_path}"
            )

            assert artifact.payload_path.exists()
            assert artifact.metadata_path.exists()
            assert artifact.payload_path.suffix == ".json"

    print(f"Successful listing JSON payloads: {successful_listing_json_count}")
    print(f"Anomalous listing responses: {len(anomalous_listing_responses)}")
    for index, status_code, listing_id, payload_path in anomalous_listing_responses:
        print(f"Anomaly [{index}] status={status_code} listing_id={listing_id} path={payload_path}")

    print(f"Exported raw listing files: {len(artifacts)}")
    print(f"Exported metadata files: {len(artifacts)}")
    print(f"Open this folder: {EXPORT_ROOT.resolve()}")

    assert len(artifacts) == len(listing_targets)
    assert successful_listing_json_count == len(listing_targets)
    assert not anomalous_listing_responses


def _looks_like_listing_json(
    *,
    payload: bytes,
    status_code: int,
    media_type: str | None,
    target_metadata: dict[str, str],
) -> bool:
    if status_code != 200:
        return False
    if media_type != "application/json":
        return False
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return False

    location = decoded.get("location")
    surface = decoded.get("surface")
    price = decoded.get("price")
    if not isinstance(location, dict):
        return False
    if not isinstance(surface, dict):
        return False
    if not isinstance(price, dict):
        return False
    if decoded.get("_id") != target_metadata["listing_id"]:
        return False
    return all(
        (
            decoded.get("title"),
            decoded.get("description"),
            price.get("total"),
            surface.get("totalSurface"),
            location.get("street"),
            location.get("lat"),
            location.get("lng"),
        )
    )
