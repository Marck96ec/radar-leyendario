from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.domain.enums import EvidenceType


class Evidence(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    source_item_id: UUID
    evidence_type: EvidenceType
    explanation: str
    confidence: float = Field(ge=0, le=100)
