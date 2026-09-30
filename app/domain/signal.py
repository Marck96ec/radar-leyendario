from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    relevance_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    topics: list[str]
    related_event_ids: list[UUID] = Field(min_length=1)
