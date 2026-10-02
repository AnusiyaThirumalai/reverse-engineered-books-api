"""HTTP client for the target website.

Responsibilities: only talk to the allow-listed host, be polite (timeouts,
spacing, User-Agent), retry transient failures a bounded number of times,
cache successful pages, and translate every failure into a domain error.
Contains NO parsing logic.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urljoin, urlparse

import httpx

from app.config import ALLOWED_HOSTS, TARGET_BASE_URL, USER_AGENT, Settings
from app.errors import (
    NotFoundError,
    UpstreamBadResponseError,
    UpstreamUnavailableError,
)
from app.services.cache import TTLCache
from app.utils.logging import get_logger

log = get_logger("scraper")

# Statuses worth retrying (transient). 400/401/403/404 are never retried.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
# Of those, the ones that mean "temporarily unavailable" rather than "broken".
_UNAVAILABLE_STATUS = {429, 502, 503, 504}


class WebsiteClient:
    def __init__(
        self,
        settings: Settings,
        cache: TTLCache[str],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._http = httpx.AsyncClient(
            transport=transport,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=httpx.Timeout(settings.request_timeout_seconds, connect=5.0),
            follow_redirects=False,  # never be bounced off the allow-listed host
        )
        self._lock = asyncio.Lock()
        self._last_request_at = 0.0

    @staticmethod
    def build_url(path: str) -> str:
        """Resolve ``path`` against the target and enforce the host allow-list."""
        url = urljoin(TARGET_BASE_URL + "/", path.lstrip("/"))
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
            raise ValueError("Refusing to fetch a URL outside the allow-listed target host")
        return url

    async def fetch_page(self, path: str) -> str:
        """Return the HTML for ``path`` (cached), or raise a domain error."""
        url = self.build_url(path)
        cached = self._cache.get(url)
        if cached is not None:
            log.info("cache hit", extra={"target_url": url, "cache": "hit"})
            return cached
        log.info("cache miss", extra={"target_url": url, "cache": "miss"})

        html = await self._fetch_with_retries(url)
        self._cache.set(url, html)
        return html

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- internals -------------------------------------------------------------

    async def _throttle(self) -> None:
        """Keep a minimum gap between upstream requests (politeness)."""
        gap = self._settings.upstream_min_interval_seconds
        async with self._lock:
            wait = self._last_request_at + gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def _fetch_with_retries(self, url: str) -> str:
        attempts = self._settings.max_retries + 1
        last_unavailable = True
        last_detail = "unknown"

        for attempt in range(1, attempts + 1):
            await self._throttle()
            try:
                resp = await self._http.get(url)
            except httpx.TimeoutException:
                last_unavailable, last_detail = True, "timeout"
            except httpx.TransportError as exc:
                last_unavailable, last_detail = True, f"connection error ({type(exc).__name__})"
            else:
                status = resp.status_code
                log.info(
                    "upstream response",
                    extra={"target_url": url, "status": status, "attempt": attempt},
                )
                if status == 200:
                    return self._validate_body(resp, url)
                if status == 404:
                    raise NotFoundError("The requested page does not exist on the target website.")
                if status not in _RETRYABLE_STATUS:
                    # 3xx / 400 / 401 / 403 / ...: do not retry, do not try to get around it.
                    raise UpstreamBadResponseError(
                        f"Target website returned an unexpected status ({status})."
                    )
                last_unavailable = status in _UNAVAILABLE_STATUS
                last_detail = f"HTTP {status}"

            if attempt < attempts:
                delay = self._settings.retry_backoff_seconds * (2 ** (attempt - 1))
                log.warning(
                    "transient upstream failure, retrying",
                    extra={"target_url": url, "detail": last_detail, "retry_in_s": delay},
                )
                await asyncio.sleep(delay)

        log.error("upstream failed", extra={"target_url": url, "detail": last_detail})
        if last_unavailable:
            raise UpstreamUnavailableError(
                f"Target website is temporarily unavailable ({last_detail})."
            )
        raise UpstreamBadResponseError(f"Target website failed ({last_detail}).")

    @staticmethod
    def _validate_body(resp: httpx.Response, url: str) -> str:
        ctype = resp.headers.get("content-type", "text/html")
        if "html" not in ctype.lower():
            raise UpstreamBadResponseError(f"Target returned non-HTML content ({ctype}).")
        # Decode explicitly as UTF-8: the site sends no charset, and a Latin-1
        # fallback turns '£' into 'Â£'.
        text = resp.content.decode("utf-8", errors="replace")
        if not text.strip():
            raise UpstreamBadResponseError("Target website returned an empty response.")
        return text
