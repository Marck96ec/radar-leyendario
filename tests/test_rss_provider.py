from datetime import datetime, timezone
from time import struct_time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.domain.enums import SourceType
from app.infrastructure.sources.config import RSSFeedConfig
from app.infrastructure.sources.rss_provider import RSSSourceProvider


FEED_ONE = RSSFeedConfig("Official AI", "https://example.test/one.xml", SourceType.OFFICIAL)
FEED_TWO = RSSFeedConfig("Tech media", "https://example.test/two.xml", SourceType.MEDIA)


def parsed_feed(*entries: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(entries=list(entries))


@pytest.mark.asyncio
async def test_rss_entries_are_normalized_and_duplicate_urls_are_removed() -> None:
    entries = [
        {
            "title": "First publication",
            "link": "https://example.test/article",
            "content": [{"value": "Full content"}],
            "published_parsed": struct_time((2026, 9, 30, 10, 20, 30, 2, 273, 0)),
        },
        {
            "title": "Updated duplicate",
            "link": "https://example.test/article",
            "summary": "Duplicate content",
        },
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        side_effect=[parsed_feed(*entries), parsed_feed()],
    ):
        items = await RSSSourceProvider([FEED_ONE, FEED_TWO]).fetch()

    assert len(items) == 1
    assert items[0].title == "First publication"
    assert items[0].content == "Full content"
    assert items[0].source_name == "Official AI"
    assert items[0].source_type is SourceType.OFFICIAL
    assert items[0].published_at == datetime(2026, 9, 30, 10, 20, 30, tzinfo=timezone.utc)
    assert items[0].published_at.tzinfo is timezone.utc


@pytest.mark.asyncio
async def test_content_precedence_and_timestamp_fallbacks_are_deterministic() -> None:
    entries = [
        {"title": "Published", "link": "https://example.test/published", "summary": "Summary", "description": "Description", "published_parsed": struct_time((2026, 1, 2, 3, 4, 5, 4, 2, 0))},
        {"title": "Updated", "link": "https://example.test/updated", "updated_parsed": struct_time((2026, 2, 3, 4, 5, 6, 1, 34, 0))},
        {"title": "Fallback", "link": "https://example.test/fallback"},
    ]

    with patch("app.infrastructure.sources.rss_provider.feedparser.parse", return_value=parsed_feed(*entries)):
        items = await RSSSourceProvider([FEED_ONE]).fetch()

    assert [item.content for item in items] == ["Summary", "Updated", "Fallback"]
    assert items[0].published_at.tzinfo is timezone.utc
    assert items[1].published_at == datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    assert items[2].published_at == datetime(1970, 1, 1, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_invalid_entries_and_failed_feeds_are_skipped() -> None:
    valid = {"title": "Valid", "link": "https://example.test/valid", "description": "Description"}
    invalid_title = {"link": "https://example.test/no-title"}
    invalid_link = {"title": "No link"}

    def parse(url: str) -> SimpleNamespace:
        if url == FEED_TWO.url:
            raise OSError("feed unavailable")
        return parsed_feed(valid, invalid_title, invalid_link)

    with patch("app.infrastructure.sources.rss_provider.feedparser.parse", side_effect=parse):
        items = await RSSSourceProvider([FEED_ONE, FEED_TWO]).fetch()

    assert [item.title for item in items] == ["Valid"]