from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EventClusterCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_item_ids: list[UUID] = Field(min_length=1)


class EventClusteringResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clusters: list[EventClusterCandidate]