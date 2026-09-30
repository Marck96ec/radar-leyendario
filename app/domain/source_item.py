from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.enums import SourceType


class SourceItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    url: str
    source_name: str
    published_at: datetime
    content: str
    source_type: SourceType
