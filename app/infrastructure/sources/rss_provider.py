import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from time import struct_time
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import httpx

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
        self._failures: list[dict[str, str]] = []
        self._enrichment_stats: dict[str, int] = {}

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
    def enrichment_stats(self) -> dict[str, int]:
        return dict(self._enrichment_stats)

    async def _enrich_sources(self, source_items: list[SourceItem]) -> list[SourceItem]:
        self._enrichment_stats = {
            "eligible": 0,
            "enriched": 0,
            "failed": 0,
            "minimum_content_chars": self._minimum_content_chars,
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
        async with httpx.AsyncClient(
            timeout=self._enrichment_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "RadarLeyendario/1.0 (+source-enrichment)"},
        ) as client:
            results = await asyncio.gather(
                *(self._enrich_item(item, client, semaphore) for item in candidates),
                return_exceptions=True,
            )

        enriched_by_id: dict[Any, str] = {}
        for item, result in zip(candidates, results):
            if isinstance(result, Exception) or not result:
                self._enrichment_stats["failed"] += 1
                if isinstance(result, Exception):
                    logger.info(
                        "RSS article enrichment failed",
                        extra={"source_url": item.url, "error": str(result)},
                    )
                continue
            enriched_by_id[item.id] = result
            self._enrichment_stats["enriched"] += 1

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
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
    ) -> str | None:
        async with semaphore:
            return await self._download_article(item.url, client)

    async def _download_article(
        self, url: str, client: httpx.AsyncClient
    ) -> str | None:
        current_url = url
        for _ in range(3):
            if not await self._is_safe_public_url(current_url):
                return None

            async with client.stream("GET", current_url) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    current_url = urljoin(current_url, location)
                    continue
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if content_type and "html" not in content_type:
                    return None

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._enrichment_max_bytes:
                        return None
                encoding = response.encoding or "utf-8"
                return extract_article_text(
                    body.decode(encoding, errors="replace"),
                    max_chars=MAX_SOURCE_CONTENT_CHARS,
                ) or None
        return None

    @staticmethod
    async def _is_safe_public_url(url: str) -> bool:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return False
        try:
            port = parsed.port
        except ValueError:
            return False
        if port not in {None, 80, 443}:
            return False

        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                parsed.hostname,
                port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except OSError:
            return False
        return bool(addresses) and all(
            ipaddress.ip_address(address[4][0]).is_global
            for address in addresses
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