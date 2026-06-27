"""Shared browser capture for HTML Bronze sources.

Bronze stays semantically blind here: the browser only expands source evidence
before persistence. Silver decides whether the final HTML contains useful facts.
"""

from __future__ import annotations

import re
import unicodedata
from time import perf_counter
from typing import Any, cast
from urllib.parse import urlparse

from inmob.bronze.contracts import BronzeRequest, BronzeResponse, TargetKind

MAX_REVEAL_CLICKS = 12
REVEAL_SETTLE_MS = 500
SAFE_REVEAL_WORDS = (
    "map",
    "mapa",
    "ubicacion",
    "location",
    "ver mas",
    "mostrar",
    "expandir",
    "caracteristicas",
    "amenities",
    "servicios",
    "escuelas",
    "restaurantes",
    "static map",
    "article map",
)
UNSAFE_CLICK_WORDS = (
    "contact",
    "contactar",
    "whatsapp",
    "telefono",
    "phone",
    "email",
    "mail",
    "login",
    "ingresar",
    "favorito",
    "share",
    "compartir",
    "download",
    "descargar",
    "avisarme",
)
REVEAL_CANDIDATE_SCRIPT = """
(clickedIds) => {
  const selector = [
    'button',
    'a',
    'summary',
    '[role="button"]',
    '[aria-expanded]',
    '[onclick]',
    '[class*="map"]',
    '[id*="map"]',
    '[class*="Map"]',
    '[id*="Map"]'
  ].join(',');
  window.__inmobRevealId = window.__inmobRevealId || 0;
  return Array.from(document.querySelectorAll(selector)).flatMap((el) => {
    if (!(el instanceof HTMLElement)) return [];
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden') return [];
    if (rect.width < 2 || rect.height < 2) return [];
    if (el.matches('[disabled],[aria-disabled="true"]')) return [];

    let id = el.getAttribute('data-inmob-reveal-id');
    if (!id) {
      id = `inmob-reveal-${window.__inmobRevealId++}`;
      el.setAttribute('data-inmob-reveal-id', id);
    }
    if (clickedIds.includes(id)) return [];

    const dataset = Object.entries(el.dataset || {})
      .map(([key, value]) => `${key} ${value || ''}`)
      .join(' ');
    return [{
      id,
      tag_name: el.tagName.toLowerCase(),
      input_type: (el.getAttribute('type') || '').toLowerCase(),
      href: el.getAttribute('href') || '',
      label: [
        el.innerText || '',
        el.getAttribute('aria-label') || '',
        el.getAttribute('title') || '',
        el.id || '',
        String(el.className || ''),
        dataset
      ].join(' ')
    }];
  });
}
"""
REVEAL_CLICK_SCRIPT = """
(id) => {
  const el = document.querySelector(`[data-inmob-reveal-id="${id}"]`);
  if (!(el instanceof HTMLElement)) return false;
  el.scrollIntoView({block: 'center', inline: 'center'});
  el.click();
  return true;
}
"""


def fetch_rendered_html(
    *,
    request: BronzeRequest,
    source_id: str,
    default_user_agent: str,
    timeout_seconds: float,
    request_logger: Any,
) -> BronzeResponse:
    """Fetch a page with Playwright and save final DOM after bounded safe reveals."""
    from playwright.sync_api import sync_playwright

    started_at = perf_counter()
    reveal_enabled = request.target.kind == TargetKind.LISTING_DETAIL
    request_logger.info(
        "Fetching target via Playwright render uri={} reveal_enabled={}",
        request.target.uri,
        reveal_enabled,
    )
    with sync_playwright() as playwright:
        request_logger.debug("Launching Chromium for browser capture")
        browser = playwright.chromium.launch(
            headless=True,
            args=("--disable-blink-features=AutomationControlled",),
        )
        try:
            context = browser.new_context(
                user_agent=request.headers.get("user-agent", default_user_agent),
                locale="es-AR",
            )
            page = context.new_page()
            extra_headers = {
                key: value for key, value in request.headers.items() if key.lower() != "user-agent"
            }
            if extra_headers:
                request_logger.debug(
                    "Setting Playwright extra headers header_names={}",
                    sorted(extra_headers),
                )
                page.set_extra_http_headers(extra_headers)

            res = page.goto(
                request.target.uri,
                wait_until="domcontentloaded",
                timeout=int(timeout_seconds * 1000),
            )
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                request_logger.debug("Network did not become idle before content capture")

            capture_metadata = {
                "browser_rendered": "true",
                "render_strategy": "playwright_content_v1",
                "render_status": "completed",
                "reveal_click_count": "0",
            }
            if reveal_enabled:
                capture_metadata["render_strategy"] = "playwright_reveal_v1"
                try:
                    click_count = reveal_dynamic_content(
                        page=page,
                        request_logger=request_logger,
                    )
                    capture_metadata["reveal_click_count"] = str(click_count)
                    request_logger.info("Reveal pass completed click_count={}", click_count)
                except Exception as exc:
                    capture_metadata["render_status"] = "partial"
                    capture_metadata["render_error"] = type(exc).__name__
                    request_logger.warning(
                        "Reveal pass failed; saving current DOM error_type={}",
                        type(exc).__name__,
                    )

            status_code = res.status if res else 500
            final_uri = page.url
            headers = res.all_headers() if res else {}
            payload = page.content().encode("utf-8")
        finally:
            browser.close()

    media_type = headers.get("content-type")
    if media_type is not None:
        media_type = media_type.split(";", maxsplit=1)[0].strip().lower()
    else:
        media_type = "text/html"

    log_method = request_logger.warning if status_code >= 400 else request_logger.info
    log_method(
        "Playwright fetch completed status_code={} media_type={} payload_bytes={} "
        "final_uri={} elapsed_seconds={}",
        status_code,
        media_type,
        len(payload),
        final_uri,
        round(perf_counter() - started_at, 3),
    )
    return BronzeResponse(
        request=request,
        status_code=status_code,
        final_uri=final_uri,
        media_type=media_type,
        headers=headers,
        capture_metadata=capture_metadata,
        payload=payload,
    )


def reveal_dynamic_content(*, page: Any, request_logger: Any) -> int:
    clicked_ids: set[str] = set()
    click_count = 0
    for _ in range(MAX_REVEAL_CLICKS):
        candidates = cast(
            list[dict[str, str]],
            page.evaluate(REVEAL_CANDIDATE_SCRIPT, sorted(clicked_ids)),
        )
        candidate = next(
            (
                item
                for item in candidates
                if is_safe_reveal_candidate(
                    item.get("label", ""),
                    tag_name=item.get("tag_name", ""),
                    href=item.get("href", ""),
                    input_type=item.get("input_type", ""),
                )
            ),
            None,
        )
        if candidate is None:
            break

        clicked_ids.add(candidate["id"])
        before_url = page.url
        clicked = bool(page.evaluate(REVEAL_CLICK_SCRIPT, candidate["id"]))
        if not clicked:
            continue

        click_count += 1
        request_logger.debug("Reveal click applied click_count={}", click_count)
        page.wait_for_timeout(REVEAL_SETTLE_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=1_000)
        except Exception:
            pass

        if not _same_document_url(before_url, page.url):
            request_logger.warning("Reveal click changed page URL; stopping reveal pass")
            try:
                page.go_back(wait_until="domcontentloaded", timeout=3_000)
            except Exception:
                pass
            break

    return click_count


def is_safe_reveal_candidate(
    label: str,
    *,
    tag_name: str = "",
    href: str = "",
    input_type: str = "",
) -> bool:
    normalized = _normalize_click_label(" ".join((label, tag_name, input_type)))
    if not normalized:
        return False
    if href and not href.startswith("#"):
        return False
    if tag_name == "input" and input_type not in {"button", "checkbox", "radio"}:
        return False
    if any(word in normalized for word in UNSAFE_CLICK_WORDS):
        return False
    return any(word in normalized for word in SAFE_REVEAL_WORDS)


def _normalize_click_label(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


def _same_document_url(left: str, right: str) -> bool:
    left_parsed = urlparse(left)
    right_parsed = urlparse(right)
    return (
        left_parsed.scheme,
        left_parsed.netloc,
        left_parsed.path,
        left_parsed.query,
    ) == (
        right_parsed.scheme,
        right_parsed.netloc,
        right_parsed.path,
        right_parsed.query,
    )
