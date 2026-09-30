from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import OpportunityCategory


class Opportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
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
    final_score: float | None = Field(default=None, ge=0, le=100)
