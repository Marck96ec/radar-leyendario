from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import EvidenceType


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    source_item_id: UUID
    evidence_type: EvidenceType
    explanation: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=100)
