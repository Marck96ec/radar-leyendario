from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.enums import OpportunityCategory


class Opportunity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    why_now: str
    category: OpportunityCategory
    impact_score: float = Field(ge=0, le=100)
    timing_score: float = Field(ge=0, le=100)
    novelty_score: float = Field(ge=0, le=100)
    content_potential: float = Field(ge=0, le=100)
    business_potential: float = Field(ge=0, le=100)
    evidence_confidence: float = Field(ge=0, le=100)
    final_score: float | None = Field(default=None, ge=0, le=100)
