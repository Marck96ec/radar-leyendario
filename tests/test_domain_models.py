from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import EvidenceType, OpportunityCategory, SourceType
from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem


@pytest.fixture
def source_item_data() -> dict[str, object]:
    return {
        "title": "New radar publication",
        "url": "https://example.com/article",
        "source_name": "Example source",
        "published_at": datetime.now(timezone.utc),
        "content": "A publication about an emerging event.",
        "source_type": SourceType.MEDIA,
    }


def test_source_item_generates_uuid(source_item_data: dict[str, object]) -> None:
    source_item = SourceItem(**source_item_data)

    assert isinstance(source_item.id, UUID)


def test_event_accepts_multiple_source_items(
    source_item_data: dict[str, object],
) -> None:
    event = Event(
        title="Grouped event",
        summary="The same event reported by multiple sources.",
        source_items=[SourceItem(**source_item_data), SourceItem(**source_item_data)],
    )

    assert isinstance(event.id, UUID)
    assert len(event.source_items) == 2


def test_signal_is_created() -> None:
    signal = Signal(
        title="Growing adoption",
        description="Several events show increasing adoption.",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["technology"],
        related_event_ids=[uuid4()],
    )

    assert isinstance(signal.id, UUID)


def test_evidence_is_created() -> None:
    evidence = Evidence(
        signal_id=uuid4(),
        source_item_id=uuid4(),
        evidence_type=EvidenceType.SUPPORTING,
        explanation="The source directly supports the signal.",
        confidence=75,
    )

    assert isinstance(evidence.id, UUID)


def test_opportunity_is_created_and_allows_missing_final_score() -> None:
    opportunity = Opportunity(
        title="Create an analysis",
        description="Publish an analysis of the signal.",
        why_now="The pattern is newly visible.",
        category=OpportunityCategory.CONTENT,
        impact_score=80,
        timing_score=90,
        novelty_score=70,
        content_potential=95,
        business_potential=40,
        evidence_confidence=85,
    )

    assert isinstance(opportunity.id, UUID)
    assert opportunity.final_score is None


@pytest.mark.parametrize("score", [-0.01, 100.01])
def test_signal_rejects_score_outside_range(score: float) -> None:
    with pytest.raises(ValidationError):
        Signal(
            title="Invalid signal",
            description="Invalid score.",
            relevance_score=score,
            novelty_score=50,
            confidence_score=50,
            topics=[],
            related_event_ids=[],
        )


@pytest.mark.parametrize("score", [-0.01, 100.01])
def test_evidence_rejects_score_outside_range(score: float) -> None:
    with pytest.raises(ValidationError):
        Evidence(
            signal_id=uuid4(),
            source_item_id=uuid4(),
            evidence_type=EvidenceType.COUNTER,
            explanation="Invalid score.",
            confidence=score,
        )


@pytest.mark.parametrize("score", [-0.01, 100.01])
def test_opportunity_rejects_score_outside_range(score: float) -> None:
    with pytest.raises(ValidationError):
        Opportunity(
            title="Invalid opportunity",
            description="Invalid score.",
            why_now="Now.",
            category=OpportunityCategory.BUSINESS,
            impact_score=score,
            timing_score=50,
            novelty_score=50,
            content_potential=50,
            business_potential=50,
            evidence_confidence=50,
        )


def test_invalid_enums_are_rejected(
    source_item_data: dict[str, object],
) -> None:
    invalid_source_item = {**source_item_data, "source_type": "invalid"}

    with pytest.raises(ValidationError):
        SourceItem(**invalid_source_item)

    with pytest.raises(ValidationError):
        Evidence(
            signal_id=uuid4(),
            source_item_id=uuid4(),
            evidence_type="invalid",
            explanation="Invalid enum.",
            confidence=50,
        )

    with pytest.raises(ValidationError):
        Opportunity(
            title="Invalid opportunity",
            description="Invalid enum.",
            why_now="Now.",
            category="invalid",
            impact_score=50,
            timing_score=50,
            novelty_score=50,
            content_potential=50,
            business_potential=50,
            evidence_confidence=50,
        )
