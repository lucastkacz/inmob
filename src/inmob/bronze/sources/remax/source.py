"""RE/MAX Argentina Bronze source adapter.

This module owns RE/MAX-specific acquisition rules: URL construction,
source identity, and technical listing discovery. It deliberately avoids
extracting real estate facts such as price, area, rooms, or address.
"""
from __future__ import annotations

import json
import re
import shutil
from collections.abc import Iterable, Sequence
from html.parser import HTMLParser
from pathlib import Path
from time import perf_counter
from urllib.parse import urljoin, urlparse

from loguru import logger

from inmob.bronze.contracts import (
    BronzeRequest,
    BronzeResponse,
    BronzeRunContext,
    BronzeTarget,
    PolitenessProfile,
    RetryProfile,
    SourceDefinition,
    TargetKind,
)
from inmob.bronze.sources.base import WebSourceRuntime
from inmob.bronze.sources.remax.search import (
    REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL,
    REMAX_API_LISTING_BY_SLUG_URL,
    REMAX_API_SEARCH_URL,
    REMAX_BUY_PATH,
    REMAX_HOME_URL,
    RemaxSearchCriteria,
)
from inmob.bronze.traffic import TrafficController
from inmob.bronze.traffic.controller import TrafficSnapshot


DEFAULT_POLITENESS = PolitenessProfile(
    requests_per_minute=12,
    burst_size=2,
    retry=RetryProfile(
        max_attempts=4,
        initial_delay_seconds=2.0,
        max_delay_seconds=45.0,
    ),
)

_LISTING_PATH_PATTERN = re.compile(
    r"(?:https?://(?:www\.)?remax\.com\.ar)?"
    r"(?P<path>/listings/[A-Za-z0-9][^\"'<>\\\s?]*)"
)
_LISTING_SLUG_PATTERN = re.compile(r'"slug"\s*:\s*"(?P<slug>[a-z0-9][a-z0-9-]*)"')
_CHROME_EXECUTABLE_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


class RemaxSource:
    """RE/MAX Argentina raw acquisition source."""

    DEFAULT_HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "es-AR,es;q=0.9,en;q=0.8",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
    }

    def __init__(
        self,
        targets: Sequence[BronzeTarget] = (),
        timeout_seconds: float = 30.0,
        traffic_controller: TrafficController | None = None,
    ) -> None:
        definition = SourceDefinition(
            source_id="remax",
            display_name="RE/MAX Argentina",
            homepage_url=REMAX_HOME_URL,
            allowed_domains=("remax.com.ar", "www.remax.com.ar", "api-ar.redremax.com"),
            politeness=DEFAULT_POLITENESS,
        )
        self._runtime = WebSourceRuntime(
            definition=definition,
            targets=targets,
            default_headers=self.DEFAULT_HEADERS,
            headers_for_target=self.headers_for_target,
            timeout_seconds=timeout_seconds,
            traffic_controller=traffic_controller,
        )

    @property
    def definition(self) -> SourceDefinition:
        return self._runtime.definition

    @property
    def default_headers(self) -> dict[str, str]:
        return self.DEFAULT_HEADERS

    def plan_requests(self, context: BronzeRunContext) -> Iterable[BronzeRequest]:
        del context
        for target in self._runtime.targets:
            yield self.build_request(target)

    def build_request(self, target: BronzeTarget) -> BronzeRequest:
        return self._runtime.build_request(target)

    def headers_for_target(self, target: BronzeTarget) -> dict[str, str]:
        hostname = urlparse(target.uri).hostname
        if target.kind == TargetKind.API_ENDPOINT or hostname == "api-ar.redremax.com":
            return {
                **self.DEFAULT_HEADERS,
                "accept": "application/json, text/plain, */*",
            }
        return self.DEFAULT_HEADERS

    def fetch(self, request: BronzeRequest) -> BronzeResponse:
        request_logger = logger.bind(
            source_id=self.definition.source_id,
            target_id=request.target.target_id,
            target_kind=request.target.kind.value,
        )
        response = self._runtime.fetch_http(request)
        if self._should_refresh_waf_session(response):
            request_logger.warning(
                "RE/MAX WAF challenge detected status_code={} uri={}",
                response.status_code,
                request.target.uri,
            )
            self._refresh_waf_session(request.target.uri)
            request_logger.info("Retrying RE/MAX fetch after WAF session refresh")
            response = self._runtime.fetch_http(request)
        return response

    def close(self) -> None:
        self._runtime.close()

    def __enter__(self) -> RemaxSource:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def traffic_snapshot(self) -> TrafficSnapshot:
        return self._runtime.traffic_snapshot()

    def reset_traffic_stats(self) -> None:
        self._runtime.reset_traffic_stats()

    @classmethod
    def listing_target(cls, *, slug: str, url: str) -> BronzeTarget:
        """Build a Bronze target for a RE/MAX listing detail page."""

        return BronzeTarget(
            target_id=f"remax-listing-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=url,
            metadata={"slug": slug},
        )

    @classmethod
    def entrepreneurship_target(cls, *, slug: str, url: str) -> BronzeTarget:
        """Build a Bronze target for a RE/MAX entrepreneurship detail page."""

        return BronzeTarget(
            target_id=f"remax-entrepreneurship-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=url,
            metadata={"slug": slug, "detail_type": "entrepreneurship"},
        )

    @classmethod
    def api_listing_target(cls, *, slug: str) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX listing detail API payload."""

        return BronzeTarget(
            target_id=f"remax-api-listing-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"{REMAX_API_LISTING_BY_SLUG_URL}/{slug}",
            metadata={
                "slug": slug,
                "public_url": _path_to_url(f"/listings/{slug}"),
                "api_url": REMAX_API_LISTING_BY_SLUG_URL,
            },
        )

    @classmethod
    def api_entrepreneurship_target(
        cls,
        *,
        slug: str,
        entity_id: str | None = None,
    ) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX entrepreneurship detail API payload."""

        metadata = {
            "slug": slug,
            "public_url": _path_to_url(f"/proyectos/{slug}"),
            "api_url": REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL,
            "detail_type": "entrepreneurship",
        }
        if entity_id:
            metadata["entity_id"] = entity_id

        return BronzeTarget(
            target_id=f"remax-api-entrepreneurship-{slug}",
            kind=TargetKind.LISTING_DETAIL,
            uri=f"{REMAX_API_ENTREPRENEURSHIP_BY_SLUG_URL}/{slug}",
            metadata=metadata,
        )

    def listing_target_from_url(self, url: str) -> BronzeTarget:
        """Build a listing target from a normalized RE/MAX listing URL."""

        slug = _listing_slug_from_url(url)
        return self.listing_target(slug=slug, url=url)

    @classmethod
    def search_target(cls, *, criteria: RemaxSearchCriteria, page: int) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX search-results page."""

        operation_ids = ",".join(
            str(operation_id) for operation_id in criteria.operation_ids
        )
        return BronzeTarget(
            target_id=f"remax-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.SEARCH_RESULTS,
            uri=criteria.build_url(page=page),
            metadata={
                "operation_ids": operation_ids,
                "page": str(page),
                "page_size": str(criteria.page_size),
                "landing_path": criteria.landing_path or "",
                "criteria_label": criteria.label or "",
            },
        )

    @classmethod
    def api_search_target(
        cls, *, criteria: RemaxSearchCriteria, page: int
    ) -> BronzeTarget:
        """Build a Bronze target for one RE/MAX API search-results page."""

        operation_ids = ",".join(
            str(operation_id) for operation_id in criteria.operation_ids
        )
        return BronzeTarget(
            target_id=f"remax-api-search-{criteria.target_key()}-page-{page}",
            kind=TargetKind.API_ENDPOINT,
            uri=criteria.build_api_url(page=page),
            metadata={
                "operation_ids": operation_ids,
                "page": str(page),
                "page_size": str(criteria.page_size),
                "landing_path": criteria.landing_path or "",
                "criteria_label": criteria.label or "",
                "api_url": REMAX_API_SEARCH_URL,
            },
        )

    @classmethod
    def search_targets(
        cls,
        *,
        criteria: RemaxSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build Bronze targets for multiple RE/MAX search-results pages."""

        return tuple(cls.search_target(criteria=criteria, page=page) for page in pages)

    @classmethod
    def api_search_targets(
        cls,
        *,
        criteria: RemaxSearchCriteria,
        pages: Sequence[int],
    ) -> tuple[BronzeTarget, ...]:
        """Build Bronze API targets for multiple RE/MAX search-results pages."""

        return tuple(cls.api_search_target(criteria=criteria, page=page) for page in pages)

    def discover_listing_targets(self, payload: bytes | str) -> tuple[BronzeTarget, ...]:
        """Discover listing-detail targets from raw RE/MAX search payloads.

        This is Bronze crawl-frontier discovery only. It extracts URLs/slugs so
        raw detail payloads can be landed later; it does not extract property
        attributes. Search API payloads produce detail API targets, while HTML
        search pages produce public detail-page targets.
        """

        text = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )
        api_targets = self._discover_api_listing_targets(text)
        if api_targets:
            logger.bind(source_id=self.definition.source_id).info(
                "RE/MAX discovery selected API detail targets count={}",
                len(api_targets),
            )
            return api_targets

        return self._discover_html_listing_targets(text)

    def discover_public_detail_targets(
        self, payload: bytes | str
    ) -> tuple[BronzeTarget, ...]:
        """Discover public HTML detail-page targets from a RE/MAX search payload."""

        text = (
            payload.decode("utf-8", errors="replace")
            if isinstance(payload, bytes)
            else payload
        )
        api_targets = self._discover_api_public_detail_targets(text)
        if api_targets:
            logger.bind(source_id=self.definition.source_id).info(
                "RE/MAX discovery selected public detail targets from API count={}",
                len(api_targets),
            )
            return api_targets

        return self._discover_html_listing_targets(text)

    def _discover_api_listing_targets(self, payload_text: str) -> tuple[BronzeTarget, ...]:
        """Discover listing detail API targets from the RE/MAX search API payload."""

        discovery_logger = logger.bind(source_id=self.definition.source_id)
        try:
            decoded = json.loads(payload_text)
        except json.JSONDecodeError:
            discovery_logger.debug("RE/MAX API discovery skipped because payload is not JSON")
            return ()

        data = decoded.get("data")
        if not isinstance(data, dict):
            discovery_logger.debug(
                "RE/MAX API discovery skipped because data is not an object data_type={}",
                type(data).__name__,
            )
            return ()

        items = data.get("data")
        if not isinstance(items, list):
            discovery_logger.debug(
                "RE/MAX API discovery skipped because data.data is not a list items_type={}",
                type(items).__name__,
            )
            return ()

        discovered: list[BronzeTarget] = []
        seen: set[str] = set()
        skipped_items = 0
        duplicate_items = 0
        entrepreneurship_items = 0
        for item in items:
            if not isinstance(item, dict):
                skipped_items += 1
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug or slug in seen:
                if isinstance(slug, str) and slug in seen:
                    duplicate_items += 1
                else:
                    skipped_items += 1
                continue
            seen.add(slug)
            entity_id = item.get("entityId")
            if item.get("entrepreneurship") is True:
                entrepreneurship_items += 1
                discovered.append(
                    self.api_entrepreneurship_target(
                        slug=slug,
                        entity_id=entity_id if isinstance(entity_id, str) else None,
                    )
                )
            else:
                discovered.append(self.api_listing_target(slug=slug))

        discovery_logger.info(
            "RE/MAX API discovery completed items={} discovered={} entrepreneurships={} "
            "skipped={} duplicates={}",
            len(items),
            len(discovered),
            entrepreneurship_items,
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)

    def _discover_api_public_detail_targets(
        self, payload_text: str
    ) -> tuple[BronzeTarget, ...]:
        """Discover public HTML detail targets from the RE/MAX search API payload."""

        discovery_logger = logger.bind(source_id=self.definition.source_id)
        try:
            decoded = json.loads(payload_text)
        except json.JSONDecodeError:
            discovery_logger.debug(
                "RE/MAX public detail discovery skipped because payload is not JSON"
            )
            return ()

        data = decoded.get("data")
        if not isinstance(data, dict):
            discovery_logger.debug(
                "RE/MAX public detail discovery skipped because data is not an object "
                "data_type={}",
                type(data).__name__,
            )
            return ()

        items = data.get("data")
        if not isinstance(items, list):
            discovery_logger.debug(
                "RE/MAX public detail discovery skipped because data.data is not a list "
                "items_type={}",
                type(items).__name__,
            )
            return ()

        discovered: list[BronzeTarget] = []
        seen: set[str] = set()
        skipped_items = 0
        duplicate_items = 0
        entrepreneurship_items = 0
        for item in items:
            if not isinstance(item, dict):
                skipped_items += 1
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug or slug in seen:
                if isinstance(slug, str) and slug in seen:
                    duplicate_items += 1
                else:
                    skipped_items += 1
                continue
            seen.add(slug)
            if item.get("entrepreneurship") is True:
                entrepreneurship_items += 1
                discovered.append(
                    self.entrepreneurship_target(
                        slug=slug,
                        url=_path_to_url(f"/proyectos/{slug}"),
                    )
                )
            else:
                discovered.append(
                    self.listing_target(
                        slug=slug,
                        url=_path_to_url(f"/listings/{slug}"),
                    )
                )

        discovery_logger.info(
            "RE/MAX API public detail discovery completed items={} discovered={} "
            "entrepreneurships={} skipped={} duplicates={}",
            len(items),
            len(discovered),
            entrepreneurship_items,
            skipped_items,
            duplicate_items,
        )
        return tuple(discovered)

    def _discover_html_listing_targets(self, html: str) -> tuple[BronzeTarget, ...]:
        discovery_logger = logger.bind(source_id=self.definition.source_id)
        parser = _RemaxListingLinkParser()
        parser.feed(html)

        discovered_urls: list[str] = []
        seen: set[str] = set()

        script_candidates = tuple(
            _path_to_url(match.group("path")) for match in _LISTING_PATH_PATTERN.finditer(html)
        )
        slug_candidates = tuple(
            _path_to_url(f"/listings/{match.group('slug')}")
            for match in _LISTING_SLUG_PATTERN.finditer(html)
        )
        rejected_candidates = 0
        duplicate_candidates = 0

        for candidate in [*parser.hrefs, *script_candidates, *slug_candidates]:
            normalized = _normalize_listing_url(candidate)
            if normalized is None:
                rejected_candidates += 1
                continue
            if normalized in seen:
                duplicate_candidates += 1
                continue
            seen.add(normalized)
            discovered_urls.append(normalized)

        discovery_logger.info(
            "RE/MAX HTML discovery completed href_candidates={} path_regex_candidates={} "
            "slug_regex_candidates={} discovered={} rejected={} duplicates={}",
            len(parser.hrefs),
            len(script_candidates),
            len(slug_candidates),
            len(discovered_urls),
            rejected_candidates,
            duplicate_candidates,
        )
        return tuple(self.listing_target_from_url(url) for url in discovered_urls)

    def _should_refresh_waf_session(self, response: BronzeResponse) -> bool:
        hostname = urlparse(response.request.target.uri).hostname
        if hostname != "www.remax.com.ar":
            return False
        if response.headers.get("x-amzn-waf-action") == "challenge":
            return True
        return response.status_code == 202 and b"awsWaf" in response.payload

    def _refresh_waf_session(self, url: str) -> None:
        waf_logger = logger.bind(source_id=self.definition.source_id)
        started_at = perf_counter()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            waf_logger.exception("Cannot refresh RE/MAX WAF session because Playwright is missing")
            raise RuntimeError(
                "RE/MAX returned an AWS WAF challenge; install playwright to refresh "
                "the browser session before retrying HTML fetches."
            ) from exc

        chrome_path = _chrome_executable_path()
        if chrome_path is None:
            waf_logger.error(
                "Cannot refresh RE/MAX WAF session because Chrome/Chromium was not found"
            )
            raise RuntimeError(
                "RE/MAX returned an AWS WAF challenge, but no Chrome/Chromium "
                "executable was found for the browser fallback."
            )

        waf_logger.info("Refreshing RE/MAX WAF session url={} chrome_path={}", url, chrome_path)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome_path,
                headless=True,
                args=("--disable-blink-features=AutomationControlled",),
            )
            context = browser.new_context(
                user_agent=self.DEFAULT_HEADERS["user-agent"],
                locale="es-AR",
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(8_000)
            cookies = context.cookies("https://www.remax.com.ar")
            browser.close()

        client = self._runtime.cached_http_client()
        if client is None:
            waf_logger.warning(
                "RE/MAX WAF session refreshed but HTTP client was not available "
                "cookies_received={} elapsed_seconds={}",
                len(cookies),
                round(perf_counter() - started_at, 3),
            )
            return

        cookies_set = 0
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            domain = cookie.get("domain")
            path = cookie.get("path")
            cookie_domain = domain if isinstance(domain, str) and domain else "www.remax.com.ar"
            cookie_path = path if isinstance(path, str) and path else "/"
            client.cookies.set(name, value, domain=cookie_domain, path=cookie_path)
            client.cookies.set(
                name,
                value,
                domain=cookie_domain.lstrip("."),
                path=cookie_path,
            )
            cookies_set += 1

        waf_logger.info(
            "RE/MAX WAF session refreshed cookies_received={} cookies_set={} "
            "elapsed_seconds={}",
            len(cookies),
            cookies_set,
            round(perf_counter() - started_at, 3),
        )


class _RemaxListingLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _path_to_url(path: str) -> str:
    return urljoin(REMAX_HOME_URL, path)


def _normalize_listing_url(candidate: str) -> str | None:
    absolute = urljoin(REMAX_HOME_URL, candidate)
    parsed = urlparse(absolute)
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    if hostname not in {"remax.com.ar", "www.remax.com.ar"}:
        return None

    path = parsed.path.rstrip("/")
    if not path.startswith("/listings/") or path == REMAX_BUY_PATH:
        return None
    if "/" in path.removeprefix("/listings/"):
        return None
    if "-" not in path.removeprefix("/listings/"):
        return None

    return f"https://www.remax.com.ar{path}"


def _listing_slug_from_url(url: str) -> str:
    normalized = _normalize_listing_url(url)
    if normalized is None:
        raise ValueError(f"URL is not a RE/MAX listing detail URL: {url}")
    return normalized.rstrip("/").split("/")[-1]


def _chrome_executable_path() -> str | None:
    for command in ("google-chrome", "chromium", "chromium-browser"):
        executable = shutil.which(command)
        if executable:
            return executable

    for candidate in _CHROME_EXECUTABLE_CANDIDATES:
        if Path(candidate).exists():
            return candidate

    return None
