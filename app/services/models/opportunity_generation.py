from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OpportunityCategory


class OpportunityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    why_now: str = Field(min_length=1)
    category: OpportunityCategory
    impact_score: float = Field(ge=0, le=100)
    timing_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)
    content_potential: float = Field(ge=0, le=100)
    business_potential: float = Field(ge=0, le=100)
    evidence_confidence: float = Field(ge=0, le=100)


class OpportunityGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunities: list[OpportunityCandidate] = Field(max_length=3)