from pathlib import Path

import pytest

from app.infrastructure.sources.config import (
    load_enabled_feeds,
    load_source_catalog,
    RSSFeedConfig,
)
from app.domain.enums import SourceType


CATALOG_PATH = Path(__file__).parents[1] / "config" / "sources.yaml"


def test_catalog_contains_all_candidates_and_filters_disabled_sources() -> None:
    catalog = load_source_catalog(CATALOG_PATH)
    enabled = load_enabled_feeds(CATALOG_PATH)

    assert len(catalog) == 16
    assert len(enabled) == 12
    assert {feed.id for feed in catalog if not feed.enabled} == {
        "anthropic",
        "infoq-ai",
        "microsoft-tech",
        "google-cloud-ai",
    }
    assert all(feed.format in {"rss", "atom"} for feed in enabled)


def test_enabled_html_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="RSS or Atom"):
        RSSFeedConfig(
            name="HTML source",
            url="https://example.test/page",
            source_type=SourceType.MEDIA,
            enabled=True,
            format="html",
        )


def test_catalog_rejects_unknown_source_type(tmp_path: Path) -> None:
    catalog = tmp_path / "sources.yaml"
    catalog.write_text(
        "sources:\n"
        "  - id: invalid\n"
        "    name: Invalid\n"
        "    url: https://example.test/feed.xml\n"
        "    category: RESEARCH\n"
        "    source_type: UNKNOWN\n"
        "    enabled: true\n"
        "    format: rss\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid source catalog entry"):
        load_source_catalog(catalog)
