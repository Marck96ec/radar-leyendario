import asyncio
import logging
from datetime import datetime, timezone
from time import struct_time
from typing import Any

import feedparser

from app.domain.source_item import SourceItem
from app.infrastructure.sources.config import RSSFeedConfig


logger = logging.getLogger(__name__)
UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class RSSSourceProvider:
    def __init__(self, feeds: list[RSSFeedConfig]) -> None:
        self._feeds = list(feeds)

    async def fetch(self) -> list[SourceItem]:
        parsed_feeds = await asyncio.gather(
            *(asyncio.to_thread(feedparser.parse, feed.url) for feed in self._feeds),
            return_exceptions=True,
        )

        source_items: list[SourceItem] = []
        seen_urls: set[str] = set()
        for feed, parsed in zip(self._feeds, parsed_feeds):
            if isinstance(parsed, Exception):
                logger.warning("RSS feed failed (%s): %s", feed.url, parsed)
                continue

            for entry in parsed.entries:
                item = self._normalize_entry(entry, feed)
                if item is not None and item.url not in seen_urls:
                    seen_urls.add(item.url)
                    source_items.append(item)

        return source_items

    @classmethod
    def _normalize_entry(
        cls, entry: Any, feed: RSSFeedConfig
    ) -> SourceItem | None:
        title = cls._text(entry.get("title"))
        url = cls._text(entry.get("link"))
        if not title or not url:
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