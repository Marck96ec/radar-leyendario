import asyncio
import logging
from datetime import datetime, timezone
from time import struct_time
from time import perf_counter
from typing import Any

import feedparser

from app.domain.source_item import SourceItem
from app.infrastructure.sources.config import RSSFeedConfig


logger = logging.getLogger(__name__)
UTC_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class RSSSourceProvider:
    def __init__(self, feeds: list[RSSFeedConfig]) -> None:
        self._feeds = list(feeds)
        self.last_report: list[dict[str, object]] = []

    async def fetch(self) -> list[SourceItem]:
        results = await asyncio.gather(
            *(self._fetch_feed(feed) for feed in self._feeds),
            return_exceptions=True,
        )

        source_items: list[SourceItem] = []
        seen_urls: set[str] = set()
        reports: list[dict[str, object]] = []
        for feed, result in zip(self._feeds, results):
            if isinstance(result, Exception):
                logger.warning("RSS feed failed (%s): %s", feed.url, result)
                reports.append(self._report(feed, "error", 0, result))
                continue

            parsed, duration_ms = result
            version = getattr(parsed, "version", None)
            entries = getattr(parsed, "entries", [])
            if not entries and (
                getattr(parsed, "bozo", False)
                or version not in {"rss", "rss10", "rss20", "atom", "atom03"}
            ):
                parser_error = getattr(parsed, "bozo_exception", None)
                if parser_error is not None and self._is_transport_error(parser_error):
                    reports.append(
                        self._report(feed, "error", 0, parser_error, duration_ms)
                    )
                    logger.warning("RSS feed failed (%s): %s", feed.url, parser_error)
                    continue
                error = ValueError("response is not a valid RSS or Atom feed")
                logger.warning("Invalid RSS feed (%s): %s", feed.url, error)
                reports.append(self._report(feed, "invalid", 0, error, duration_ms))
                continue

            recovered = 0
            for entry in entries:
                item = self._normalize_entry(entry, feed)
                if item is not None and item.url not in seen_urls:
                    seen_urls.add(item.url)
                    source_items.append(item)
                    recovered += 1
            reports.append(self._report(feed, "ok", recovered, duration_ms=duration_ms))

        self.last_report = reports
        return source_items

    @staticmethod
    async def _fetch_feed(feed: RSSFeedConfig):
        started = perf_counter()
        parsed = await asyncio.to_thread(feedparser.parse, feed.url)
        return parsed, round((perf_counter() - started) * 1000, 2)

    @staticmethod
    def _report(
        feed: RSSFeedConfig,
        status: str,
        articles_recovered: int,
        error: Exception | None = None,
        duration_ms: float = 0,
    ) -> dict[str, object]:
        report: dict[str, object] = {
            "source_id": feed.id or feed.name,
            "source_name": feed.name,
            "status": status,
            "articles_recovered": articles_recovered,
            "duration_ms": duration_ms,
            "queried_at": datetime.now(timezone.utc).isoformat(),
        }
        if error is not None:
            report["error"] = f"{type(error).__name__}: {error}"
        return report

    @staticmethod
    def _is_transport_error(error: Exception) -> bool:
        message = str(error).lower()
        return any(
            marker in message
            for marker in ("urlopen error", "certificate_verify_failed", "timed out")
        )

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
            category=feed.category,
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