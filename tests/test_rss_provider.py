import logging
import time
from datetime import datetime, timedelta, timezone
from time import struct_time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.domain.enums import SourceType
from app.infrastructure.sources.config import RSSFeedConfig
from app.infrastructure.sources.rss_provider import RSSSourceProvider


FEED_ONE = RSSFeedConfig("Official AI", "https://example.test/one.xml", SourceType.OFFICIAL)
FEED_TWO = RSSFeedConfig("Tech media", "https://example.test/two.xml", SourceType.MEDIA)
NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def parsed_feed(*entries: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(entries=list(entries))


def entry(title: str, url: str, published_at: datetime | None = None) -> dict[str, object]:
    data: dict[str, object] = {"title": title, "link": url, "summary": title}
    if published_at is not None:
        data["published_parsed"] = published_at.timetuple()
    return data


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


@pytest.mark.asyncio
async def test_feed_timeout_is_recorded_without_blocking_other_results() -> None:
    def parse(url: str) -> SimpleNamespace:
        if url == FEED_ONE.url:
            time.sleep(0.2)
        return parsed_feed(
            {
                "title": "Fast result",
                "link": "https://example.test/fast",
            }
        )

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse", side_effect=parse
    ):
        provider = RSSSourceProvider([FEED_ONE, FEED_TWO], timeout_seconds=0.1)
        items = await provider.fetch()

    assert [item.url for item in items] == ["https://example.test/fast"]
    assert provider.failures[0]["source"] == "Official AI"


def _frozen_clock() -> datetime:
    return NOW


@pytest.mark.parametrize(
    "kwarg",
    ["max_items_per_feed", "max_item_age_hours", "max_total_items"],
)
def test_non_positive_volume_limits_are_rejected(kwarg: str) -> None:
    with pytest.raises(ValueError):
        RSSSourceProvider([FEED_ONE], **{kwarg: 0})


@pytest.mark.asyncio
async def test_items_are_ordered_by_published_date_not_feed_position() -> None:
    entries = [
        entry("Oldest", "https://example.test/oldest", NOW - timedelta(hours=10)),
        entry("Newest", "https://example.test/newest", NOW - timedelta(hours=1)),
        entry("Middle", "https://example.test/middle", NOW - timedelta(hours=5)),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider(
            [FEED_ONE],
            max_items_per_feed=10,
            max_item_age_hours=72,
            max_total_items=10,
            clock=_frozen_clock,
        )
        items = await provider.fetch()

    assert [item.title for item in items] == ["Newest", "Middle", "Oldest"]


@pytest.mark.asyncio
async def test_items_without_a_valid_date_are_treated_as_unknown_and_discarded() -> None:
    entries = [
        entry("Recent", "https://example.test/recent", NOW - timedelta(hours=1)),
        entry("No date", "https://example.test/no-date", published_at=None),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider(
            [FEED_ONE], max_item_age_hours=72, clock=_frozen_clock
        )
        items = await provider.fetch()

    assert [item.title for item in items] == ["Recent"]


@pytest.mark.asyncio
async def test_items_older_than_max_age_are_discarded() -> None:
    entries = [
        entry("Within window", "https://example.test/in", NOW - timedelta(hours=71)),
        entry("Too old", "https://example.test/out", NOW - timedelta(hours=73)),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider(
            [FEED_ONE], max_item_age_hours=72, clock=_frozen_clock
        )
        items = await provider.fetch()

    assert [item.title for item in items] == ["Within window"]


@pytest.mark.asyncio
async def test_max_items_per_feed_keeps_the_most_recent_per_source() -> None:
    entries = [
        entry(f"Article {index}", f"https://example.test/one/{index}", NOW - timedelta(hours=index))
        for index in range(5)
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider([FEED_ONE], max_items_per_feed=2, clock=_frozen_clock)
        items = await provider.fetch()

    assert [item.title for item in items] == ["Article 0", "Article 1"]


@pytest.mark.asyncio
async def test_max_items_per_feed_applies_independently_to_each_source() -> None:
    feed_one_entries = [
        entry(f"One {index}", f"https://example.test/one/{index}", NOW - timedelta(hours=index))
        for index in range(4)
    ]
    feed_two_entries = [
        entry(f"Two {index}", f"https://example.test/two/{index}", NOW - timedelta(hours=index))
        for index in range(4)
    ]

    def parse(url: str) -> SimpleNamespace:
        if url == FEED_ONE.url:
            return parsed_feed(*feed_one_entries)
        return parsed_feed(*feed_two_entries)

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse", side_effect=parse
    ):
        provider = RSSSourceProvider(
            [FEED_ONE, FEED_TWO],
            max_items_per_feed=2,
            max_total_items=100,
            clock=_frozen_clock,
        )
        items = await provider.fetch()

    titles_by_feed = {FEED_ONE.name: 0, FEED_TWO.name: 0}
    for item in items:
        titles_by_feed[item.source_name] += 1

    assert titles_by_feed == {FEED_ONE.name: 2, FEED_TWO.name: 2}


@pytest.mark.asyncio
async def test_max_total_items_caps_combined_results_across_sources() -> None:
    feed_one_entries = [
        entry(f"One {index}", f"https://example.test/one/{index}", NOW - timedelta(hours=index))
        for index in range(5)
    ]
    feed_two_entries = [
        entry(f"Two {index}", f"https://example.test/two/{index}", NOW - timedelta(hours=index + 0.5))
        for index in range(5)
    ]

    def parse(url: str) -> SimpleNamespace:
        if url == FEED_ONE.url:
            return parsed_feed(*feed_one_entries)
        return parsed_feed(*feed_two_entries)

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse", side_effect=parse
    ):
        provider = RSSSourceProvider(
            [FEED_ONE, FEED_TWO],
            max_items_per_feed=10,
            max_total_items=4,
            clock=_frozen_clock,
        )
        items = await provider.fetch()

    assert len(items) == 4
    assert [item.title for item in items] == ["One 0", "Two 0", "One 1", "Two 1"]


@pytest.mark.asyncio
async def test_duplicate_urls_are_removed_when_volume_filters_are_enabled() -> None:
    entries = [
        entry("First", "https://example.test/same", NOW - timedelta(hours=1)),
        entry("Duplicate", "https://example.test/same", NOW - timedelta(hours=2)),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider(
            [FEED_ONE], max_items_per_feed=10, max_total_items=10, clock=_frozen_clock
        )
        items = await provider.fetch()

    assert [item.title for item in items] == ["First"]


@pytest.mark.asyncio
async def test_empty_feed_does_not_break_filtering_of_other_feeds() -> None:
    feed_two_entries = [entry("Two 0", "https://example.test/two/0", NOW - timedelta(hours=1))]

    def parse(url: str) -> SimpleNamespace:
        if url == FEED_ONE.url:
            return parsed_feed()
        return parsed_feed(*feed_two_entries)

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse", side_effect=parse
    ):
        provider = RSSSourceProvider(
            [FEED_ONE, FEED_TWO],
            max_items_per_feed=10,
            max_item_age_hours=72,
            max_total_items=10,
            clock=_frozen_clock,
        )
        items = await provider.fetch()

    assert [item.title for item in items] == ["Two 0"]


@pytest.mark.asyncio
async def test_source_volume_is_logged_per_feed(caplog: pytest.LogCaptureFixture) -> None:
    entries = [
        entry("Within window", "https://example.test/in", NOW - timedelta(hours=1)),
        entry("Too old", "https://example.test/out", NOW - timedelta(hours=100)),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        provider = RSSSourceProvider(
            [FEED_ONE], max_item_age_hours=72, clock=_frozen_clock
        )
        with caplog.at_level(logging.INFO, logger="app.infrastructure.sources.rss_provider"):
            await provider.fetch()

    volume_records = [r for r in caplog.records if r.message == "RSS source volume"]
    assert len(volume_records) == 1
    record = volume_records[0]
    assert record.source_name == FEED_ONE.name
    assert record.retrieved == 2
    assert record.accepted == 1
    assert record.discarded == 1


@pytest.mark.asyncio
async def test_without_volume_limits_legacy_order_and_behavior_is_preserved() -> None:
    entries = [
        entry("Oldest", "https://example.test/oldest", NOW - timedelta(hours=10)),
        entry("Newest", "https://example.test/newest", NOW - timedelta(hours=1)),
    ]

    with patch(
        "app.infrastructure.sources.rss_provider.feedparser.parse",
        return_value=parsed_feed(*entries),
    ):
        items = await RSSSourceProvider([FEED_ONE]).fetch()

    assert [item.title for item in items] == ["Oldest", "Newest"]