import json

import pytest

from app.domain.enums import SourceType
from app.infrastructure.sources.config import RSSFeedConfig, load_rss_feeds


def test_load_rss_feeds_from_json() -> None:
    feeds = load_rss_feeds(
        json.dumps(
            [
                {
                    "name": "Example",
                    "url": "https://example.test/feed.xml",
                    "source_type": "media",
                }
            ]
        )
    )

    assert feeds == [
        RSSFeedConfig("Example", "https://example.test/feed.xml", SourceType.MEDIA)
    ]


@pytest.mark.parametrize(
    "raw_config",
    ["not-json", "{}", json.dumps([{"name": "missing url"}])],
)
def test_invalid_feed_configuration_is_rejected(raw_config: str) -> None:
    with pytest.raises(ValueError):
        load_rss_feeds(raw_config)


def test_feed_urls_must_be_absolute_http_urls() -> None:
    with pytest.raises(ValueError):
        RSSFeedConfig("Example", "file:///tmp/feed.xml", SourceType.MEDIA)
