from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.source_item import SourceItem


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_items: list[SourceItem] = Field(min_length=1)
