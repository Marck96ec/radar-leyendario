from dataclasses import dataclass

from app.domain.enums import SourceType


@dataclass(frozen=True)
class RSSFeedConfig:
    name: str
    url: str
    source_type: SourceType