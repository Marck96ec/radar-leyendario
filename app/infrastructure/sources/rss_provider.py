import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import struct_time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpcore
import httpx
from httpcore._backends.auto import AutoBackend

from app.domain.source_item import SourceItem
from app.infrastructure.sources.config import RSSFeedConfig
from app.services.source_content import (
    MAX_SOURCE_CONTENT_CHARS,
    MIN_SOURCE_CONTENT_CHARS,
    clean_source_text,
    extract_article_text,
    has_sufficient_source_content,
)


logger = logging.getLogger(__name__)
UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
DEFAULT_ENRICHMENT_MAX_REDIRECTS = 3


@dataclass(frozen=True)
class _ResolvedPublicURL:
    hostname: str
    port: int
    address: str


@dataclass(frozen=True)
class _EnrichmentResult:
    content: str | None
    failure_reason: str | None = None


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect only to addresses resolved and approved for the current request."""

    def __init__(self) -> None:
        self._backend = AutoBackend()
        self._pinned_addresses: dict[tuple[str, int], str] = {}

    def pin(self, resolved_url: _ResolvedPublicURL) -> None:
        self._pinned_addresses[
            (resolved_url.hostname.lower().rstrip("."), resolved_url.port)
        ] = resolved_url.address

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        address = self._pinned_addresses.get((host.lower().rstrip("."), port))
        if address is None:
            raise OSError("Unvalidated destination")
        return await self._backend.connect_tcp(
            address, port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(path, timeout, socket_options)

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, backend: _PinnedNetworkBackend) -> None:
        super().__init__(retries=0, trust_env=False)
        self._pool._network_backend = backend


class RSSSourceProvider:
    def __init__(
        self,
        feeds: list[RSSFeedConfig],
        timeout_seconds: float = 15.0,
        max_items_per_feed: int | None = None,
        max_item_age_hours: float | None = None,
        max_total_items: int | None = None,
        clock: Callable[[], datetime] | None = None,
        enrich_official_content: bool = True,
        enrichment_timeout_seconds: float = 5.0,
        enrichment_max_bytes: int = 1_000_000,
        enrichment_concurrency: int = 4,
        minimum_content_chars: int = MIN_SOURCE_CONTENT_CHARS,
        enrichment_max_redirects: int = DEFAULT_ENRICHMENT_MAX_REDIRECTS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("RSS timeout must be greater than zero")
        if max_items_per_feed is not None and max_items_per_feed <= 0:
            raise ValueError("RSS max items per feed must be greater than zero")
        if max_item_age_hours is not None and max_item_age_hours <= 0:
            raise ValueError("RSS max item age hours must be greater than zero")
        if max_total_items is not None and max_total_items <= 0:
            raise ValueError("RSS max total items must be greater than zero")
        if enrichment_timeout_seconds <= 0:
            raise ValueError("RSS enrichment timeout must be greater than zero")
        if enrichment_max_bytes <= 0:
            raise ValueError("RSS enrichment max bytes must be greater than zero")
        if enrichment_concurrency <= 0:
            raise ValueError("RSS enrichment concurrency must be greater than zero")
        if minimum_content_chars <= 0:
            raise ValueError("RSS minimum content chars must be greater than zero")
        if enrichment_max_redirects < 0:
            raise ValueError("RSS enrichment max redirects must not be negative")
        self._feeds = list(feeds)
        self._timeout_seconds = timeout_seconds
        self._max_items_per_feed = max_items_per_feed
        self._max_item_age_hours = max_item_age_hours
        self._max_total_items = max_total_items
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._enrich_official_content = enrich_official_content
        self._enrichment_timeout_seconds = enrichment_timeout_seconds
        self._enrichment_max_bytes = enrichment_max_bytes
        self._enrichment_concurrency = enrichment_concurrency
        self._minimum_content_chars = minimum_content_chars
        self._enrichment_max_redirects = enrichment_max_redirects
        self._failures: list[dict[str, str]] = []
        self._enrichment_stats: dict[str, object] = {}

    async def fetch(self) -> list[SourceItem]:
        self._failures = []
        parsed_feeds = await asyncio.gather(
            *(
                self._fetch_feed(feed)
                for feed in self._feeds
            ),
            return_exceptions=True,
        )

        seen_urls: set[str] = set()
        items_by_feed: dict[str, list[SourceItem]] = {}
        retrieved_by_feed: dict[str, int] = {}
        for feed, parsed in zip(self._feeds, parsed_feeds):
            if isinstance(parsed, Exception):
                error_message = str(parsed) or type(parsed).__name__
                failure = {
                    "source": feed.name,
                    "url": feed.url,
                    "error": error_message,
                }
                self._failures.append(failure)
                logger.warning(
                    "RSS feed failed",
                    extra={"source_name": feed.name, "source_url": feed.url},
                    exc_info=parsed,
                )
                continue

            parser_error = getattr(parsed, "bozo_exception", None)
            if parser_error:
                failure = {
                    "source": feed.name,
                    "url": feed.url,
                    "error": str(parser_error),
                }
                self._failures.append(failure)
                logger.warning(
                    "RSS feed returned a parser warning",
                    extra={"source_name": feed.name, "source_url": feed.url},
                )

            feed_items: list[SourceItem] = []
            for entry in parsed.entries:
                item = self._normalize_entry(entry, feed)
                canonical_url = self._canonical_url(item.url) if item else None
                if item is not None and canonical_url not in seen_urls:
                    seen_urls.add(canonical_url)
                    feed_items.append(item)

            retrieved_by_feed[feed.name] = len(parsed.entries)
            items_by_feed.setdefault(feed.name, []).extend(feed_items)

        source_items, accepted_by_feed = self._apply_volume_filters(items_by_feed)
        self._log_volume_stats(retrieved_by_feed, accepted_by_feed)
        source_items = await self._enrich_sources(source_items)
        return source_items

    @property
    def failures(self) -> list[dict[str, str]]:
        return list(self._failures)

    @property
    def enrichment_stats(self) -> dict[str, object]:
        return dict(self._enrichment_stats)

    async def _enrich_sources(self, source_items: list[SourceItem]) -> list[SourceItem]:
        self._enrichment_stats = {
            "eligible": 0,
            "enriched": 0,
            "failed": 0,
            "minimum_content_chars": self._minimum_content_chars,
            "failure_reasons": {},
        }
        if not self._enrich_official_content:
            return source_items

        candidates = [
            item
            for item in source_items
            if item.source_type.value == "OFFICIAL"
            and not has_sufficient_source_content(
                item.content, minimum_chars=self._minimum_content_chars
            )
        ]
        self._enrichment_stats["eligible"] = len(candidates)
        if not candidates:
            return source_items

        semaphore = asyncio.Semaphore(self._enrichment_concurrency)
        results = await asyncio.gather(
            *(self._enrich_item(item, semaphore) for item in candidates),
            return_exceptions=True,
        )

        enriched_by_id: dict[Any, str] = {}
        for item, result in zip(candidates, results):
            if isinstance(result, Exception):
                self._record_enrichment_failure(
                    "transport_error",
                    item.url,
                    error=result,
                )
                continue
            content = result.content if isinstance(result, _EnrichmentResult) else result
            if not isinstance(content, str) or not content:
                reason = (
                    result.failure_reason
                    if isinstance(result, _EnrichmentResult)
                    else "empty_extraction"
                )
                self._record_enrichment_failure(reason or "empty_extraction", item.url)
                continue
            enriched_by_id[item.id] = content
            self._enrichment_stats["enriched"] = (
                int(self._enrichment_stats["enriched"]) + 1
            )

        return [
            item.model_copy(
                update={
                    "content": enriched_by_id.get(item.id, item.content)[
                        :MAX_SOURCE_CONTENT_CHARS
                    ]
                }
            )
            for item in source_items
        ]

    async def _enrich_item(
        self,
        item: SourceItem,
        semaphore: asyncio.Semaphore,
    ) -> _EnrichmentResult:
        async with semaphore:
            backend = _PinnedNetworkBackend()
            transport = _PinnedAsyncHTTPTransport(backend)
            async with httpx.AsyncClient(
                timeout=self._enrichment_timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": "RadarLeyendario/1.0 (+source-enrichment)"},
                transport=transport,
                trust_env=False,
            ) as client:
                try:
                    return await self._download_article(item.url, client, backend)
                except httpx.TimeoutException:
                    return _EnrichmentResult(None, "timeout")
                except httpx.RequestError:
                    return _EnrichmentResult(None, "transport_error")
                except OSError:
                    return _EnrichmentResult(None, "transport_error")

    async def _download_article(
        self,
        url: str,
        client: httpx.AsyncClient,
        backend: _PinnedNetworkBackend,
    ) -> _EnrichmentResult:
        current_url = url
        redirects_followed = 0
        while True:
            resolved_url, failure_reason = await self._resolve_public_url(current_url)
            if resolved_url is None:
                return _EnrichmentResult(None, failure_reason)
            backend.pin(resolved_url)

            try:
                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirects_followed >= self._enrichment_max_redirects:
                            return _EnrichmentResult(None, "redirect_limit")
                        location = response.headers.get("location")
                        if not location:
                            return _EnrichmentResult(None, "invalid_redirect")
                        current_url = urljoin(current_url, location)
                        redirects_followed += 1
                        continue
                    if response.status_code == 403:
                        return _EnrichmentResult(None, "http_403")
                    if response.status_code == 429:
                        return _EnrichmentResult(None, "http_429")
                    if 500 <= response.status_code <= 599:
                        return _EnrichmentResult(None, "http_5xx")
                    if response.status_code != 200:
                        return _EnrichmentResult(None, f"http_{response.status_code}")
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    )
                    if content_type and content_type not in {
                        "text/html",
                        "application/xhtml+xml",
                    }:
                        return _EnrichmentResult(None, "invalid_content_type")

                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            if int(content_length) > self._enrichment_max_bytes:
                                return _EnrichmentResult(None, "response_too_large")
                        except ValueError:
                            pass

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._enrichment_max_bytes:
                            return _EnrichmentResult(None, "response_too_large")
                    encoding = response.encoding or "utf-8"
                    content = extract_article_text(
                        body.decode(encoding, errors="replace"),
                        max_chars=MAX_SOURCE_CONTENT_CHARS,
                    )
                    return _EnrichmentResult(
                        content or None,
                        None if content else "empty_extraction",
                    )
            except httpx.TimeoutException:
                return _EnrichmentResult(None, "timeout")
            except httpx.RequestError:
                return _EnrichmentResult(None, "transport_error")
            except OSError:
                return _EnrichmentResult(None, "transport_error")

    def _record_enrichment_failure(
        self,
        reason: str,
        url: str,
        *,
        error: Exception | None = None,
    ) -> None:
        self._enrichment_stats["failed"] = int(self._enrichment_stats["failed"]) + 1
        failure_reasons = self._enrichment_stats["failure_reasons"]
        if not isinstance(failure_reasons, dict):
            failure_reasons = {}
            self._enrichment_stats["failure_reasons"] = failure_reasons
        failure_reasons[reason] = int(failure_reasons.get(reason, 0)) + 1
        logger.info(
            "RSS article enrichment failed",
            extra={
                "source_url": url,
                "failure_reason": reason,
                **({"error": str(error)} if error is not None else {}),
            },
        )

    @staticmethod
    async def _is_safe_public_url(url: str) -> bool:
        resolved_url, _ = await RSSSourceProvider._resolve_public_url(url)
        return resolved_url is not None

    @staticmethod
    async def _resolve_public_url(
        url: str,
    ) -> tuple[_ResolvedPublicURL | None, str]:
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
        except ValueError:
            return None, "unsafe_url"
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username
            or parsed.password
        ):
            return None, "unsafe_url"
        try:
            port = parsed.port
        except ValueError:
            return None, "unsafe_url"
        if port not in {None, 80, 443}:
            return None, "unsafe_url"

        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                hostname,
                port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror:
            return None, "dns_error"
        except OSError:
            return None, "dns_error"

        if not addresses:
            return None, "dns_error"
        resolved_addresses = [address[4][0] for address in addresses]
        try:
            if not all(ipaddress.ip_address(address).is_global for address in resolved_addresses):
                return None, "unsafe_url"
        except ValueError:
            return None, "unsafe_url"
        return (
            _ResolvedPublicURL(
                hostname=hostname,
                port=port or (443 if parsed.scheme == "https" else 80),
                address=resolved_addresses[0],
            ),
            "",
        )

    def _apply_volume_filters(
        self, items_by_feed: dict[str, list[SourceItem]]
    ) -> tuple[list[SourceItem], dict[str, list[SourceItem]]]:
        filters_enabled = (
            self._max_items_per_feed is not None
            or self._max_item_age_hours is not None
            or self._max_total_items is not None
        )
        if not filters_enabled:
            source_items = [
                item
                for feed in self._feeds
                for item in items_by_feed.get(feed.name, [])
            ]
            return source_items, items_by_feed

        cutoff: datetime | None = None
        if self._max_item_age_hours is not None:
            cutoff = self._clock() - timedelta(hours=self._max_item_age_hours)

        per_feed_filtered: dict[str, list[SourceItem]] = {}
        for feed in self._feeds:
            # Sort by publication date, not feed position, so the most recent
            # items survive the per-feed cap. Unknown dates (UTC_EPOCH) sort
            # last instead of being assumed recent.
            feed_items = sorted(
                items_by_feed.get(feed.name, []),
                key=lambda item: item.published_at,
                reverse=True,
            )
            if cutoff is not None:
                feed_items = [item for item in feed_items if item.published_at >= cutoff]
            if self._max_items_per_feed is not None:
                feed_items = feed_items[: self._max_items_per_feed]
            per_feed_filtered[feed.name] = feed_items

        combined = sorted(
            (item for feed in self._feeds for item in per_feed_filtered[feed.name]),
            key=lambda item: item.published_at,
            reverse=True,
        )
        if self._max_total_items is not None:
            combined = combined[: self._max_total_items]

        accepted_by_feed: dict[str, list[SourceItem]] = {}
        for item in combined:
            accepted_by_feed.setdefault(item.source_name, []).append(item)

        return combined, accepted_by_feed

    def _log_volume_stats(
        self,
        retrieved_by_feed: dict[str, int],
        accepted_by_feed: dict[str, list[SourceItem]],
    ) -> None:
        for feed in self._feeds:
            if feed.name not in retrieved_by_feed:
                continue
            retrieved = retrieved_by_feed[feed.name]
            accepted = len(accepted_by_feed.get(feed.name, []))
            discarded = retrieved - accepted
            logger.info(
                "RSS source volume",
                extra={
                    "source_name": feed.name,
                    "source_url": feed.url,
                    "retrieved": retrieved,
                    "accepted": accepted,
                    "discarded": discarded,
                },
            )

    async def _fetch_feed(self, feed: RSSFeedConfig) -> Any:
        return await asyncio.wait_for(
            asyncio.to_thread(feedparser.parse, feed.url),
            timeout=self._timeout_seconds,
        )

    @classmethod
    def _normalize_entry(
        cls, entry: Any, feed: RSSFeedConfig
    ) -> SourceItem | None:
        title = cls._text(entry.get("title"))
        url = cls._text(entry.get("link"))
        if not title or not cls._is_http_url(url):
            return None

        content = clean_source_text(cls._entry_content(entry)) or title
        return SourceItem(
            title=title,
            url=url,
            source_name=feed.name,
            published_at=cls._published_at(entry),
            content=content,
            source_type=feed.source_type,
        )

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @classmethod
    def _canonical_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                parsed.query,
                "",
            )
        )

    @staticmethod
    def _text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @classmethod
    def _entry_content(cls, entry: Any) -> str:
        content = entry.get("content")
        if isinstance(content, list):
            for value in content:
                candidate = cls._text(value.get("value") if isinstance(value, dict) else value)
                if candidate:
                    return candidate
        elif (candidate := cls._text(content)):
            return candidate

        for field in ("summary", "description"):
            if candidate := cls._text(entry.get(field)):
                return candidate
        return ""

    @staticmethod
    def _published_at(entry: Any) -> datetime:
        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if isinstance(parsed, struct_time):
                try:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    continue

        # A deterministic UTC epoch is preferable to silently claiming a current time.
        return UTC_EPOCH