import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from time import struct_time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser

from app.domain.source_item import SourceItem
from app.infrastructure.sources.config import RSSFeedConfig


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
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("RSS timeout must be greater than zero")
        if max_items_per_feed is not None and max_items_per_feed <= 0:
            raise ValueError("RSS max items per feed must be greater than zero")
        if max_item_age_hours is not None and max_item_age_hours <= 0:
            raise ValueError("RSS max item age hours must be greater than zero")
        if max_total_items is not None and max_total_items <= 0:
            raise ValueError("RSS max total items must be greater than zero")
        self._feeds = list(feeds)
        self._timeout_seconds = timeout_seconds
        self._max_items_per_feed = max_items_per_feed
        self._max_item_age_hours = max_item_age_hours
        self._max_total_items = max_total_items
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._failures: list[dict[str, str]] = []

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
        return source_items

    @property
    def failures(self) -> list[dict[str, str]]:
        return list(self._failures)

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

        content = cls._entry_content(entry) or title
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