import asyncio
import logging
from datetime import datetime, timezone
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
        self, feeds: list[RSSFeedConfig], timeout_seconds: float = 15.0
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("RSS timeout must be greater than zero")
        self._feeds = list(feeds)
        self._timeout_seconds = timeout_seconds
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

        source_items: list[SourceItem] = []
        seen_urls: set[str] = set()
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

            for entry in parsed.entries:
                item = self._normalize_entry(entry, feed)
                canonical_url = self._canonical_url(item.url) if item else None
                if item is not None and canonical_url not in seen_urls:
                    seen_urls.add(canonical_url)
                    source_items.append(item)

        return source_items

    @property
    def failures(self) -> list[dict[str, str]]:
        return list(self._failures)

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