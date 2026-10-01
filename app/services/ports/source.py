from typing import Protocol

from app.domain.source_item import SourceItem


class SourceProvider(Protocol):
    async def fetch(self) -> list[SourceItem]:
        ...