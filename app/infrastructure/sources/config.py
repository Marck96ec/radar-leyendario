from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domain.enums import SourceType


@dataclass(frozen=True)
class RSSFeedConfig:
    name: str
    url: str
    source_type: SourceType
    id: str = ""
    category: str = "UNCATEGORIZED"
    enabled: bool = True
    format: str = "rss"
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.url.strip():
            raise ValueError("RSS feed name and URL are required")
        if self.format not in {"rss", "atom", "html"}:
            raise ValueError(f"Unsupported source format: {self.format}")
        if self.enabled and self.format == "html":
            raise ValueError("Enabled sources must provide an RSS or Atom feed")

DEFAULT_SOURCES_PATH = Path(__file__).resolve().parents[3] / "config" / "sources.yaml"


def load_source_catalog(path: Path | str = DEFAULT_SOURCES_PATH) -> list[RSSFeedConfig]:
    with Path(path).open(encoding="utf-8") as source_file:
        document: Any = yaml.safe_load(source_file)

    if not isinstance(document, dict) or not isinstance(document.get("sources"), list):
        raise ValueError("Source catalog must contain a 'sources' list")

    catalog: list[RSSFeedConfig] = []
    for raw_source in document["sources"]:
        if not isinstance(raw_source, dict):
            raise ValueError("Each source catalog entry must be an object")
        try:
            catalog.append(
                RSSFeedConfig(
                    id=str(raw_source["id"]),
                    name=str(raw_source["name"]),
                    url=str(raw_source["url"]),
                    category=str(raw_source["category"]),
                    source_type=SourceType(str(raw_source["source_type"])),
                    enabled=bool(raw_source["enabled"]),
                    format=str(raw_source["format"]).lower(),
                    reason=(str(raw_source["reason"]) if raw_source.get("reason") else None),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid source catalog entry: {raw_source!r}") from exc
    return catalog


def load_enabled_feeds(path: Path | str = DEFAULT_SOURCES_PATH) -> list[RSSFeedConfig]:
    return [feed for feed in load_source_catalog(path) if feed.enabled]