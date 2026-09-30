from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Signal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    relevance_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    topics: list[str]
    related_event_ids: list[UUID]
