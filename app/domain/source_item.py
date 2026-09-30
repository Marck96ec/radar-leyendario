from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SourceType


class SourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    published_at: datetime
    content: str = Field(min_length=1)
    source_type: SourceType
