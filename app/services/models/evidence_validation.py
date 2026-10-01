from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import EvidenceType


class EvidenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    source_item_id: UUID
    evidence_type: EvidenceType
    explanation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=100)


class EvidenceValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: list[EvidenceCandidate]