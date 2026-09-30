from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.source_item import SourceItem


class Event(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    summary: str
    source_items: list[SourceItem]
