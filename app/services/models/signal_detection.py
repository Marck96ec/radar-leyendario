from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SignalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    relevance_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    topics: list[str]
    related_event_ids: list[UUID] = Field(min_length=1)


class SignalDetectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[SignalCandidate] = Field(max_length=5)