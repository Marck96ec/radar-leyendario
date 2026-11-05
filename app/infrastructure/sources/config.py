import json
from dataclasses import dataclass
from urllib.parse import urlparse

from app.domain.enums import SourceType


@dataclass(frozen=True)
class RSSFeedConfig:
    name: str
    url: str
    source_type: SourceType

    def __post_init__(self) -> None:
        name = self.name.strip()
        url = self.url.strip()
        source_type = (
            self.source_type
            if isinstance(self.source_type, SourceType)
            else SourceType(str(self.source_type).upper())
        )
        if not name:
            raise ValueError("RSS feed name must not be empty")
        parsed_url = urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError(f"RSS feed URL must be an absolute HTTP(S) URL: {url}")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "source_type", source_type)


def load_rss_feeds(raw_config: str) -> list[RSSFeedConfig]:
    """Parse the JSON feed configuration supplied by the deployment environment."""
    if not raw_config.strip():
        return []

    try:
        entries = json.loads(raw_config)
    except json.JSONDecodeError as exc:
        raise ValueError("RSS_FEEDS must contain a valid JSON array") from exc

    if not isinstance(entries, list):
        raise ValueError("RSS_FEEDS must contain a JSON array")

    feeds: list[RSSFeedConfig] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"RSS feed at index {index} must be an object")
        try:
            feeds.append(
                RSSFeedConfig(
                    name=str(entry["name"]),
                    url=str(entry["url"]),
                    source_type=SourceType(str(entry["source_type"]).upper()),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid RSS feed at index {index}") from exc
    return feeds