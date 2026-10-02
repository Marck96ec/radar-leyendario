from datetime import datetime, timezone
from uuid import uuid4

from app.domain.enums import EvidenceType, OpportunityCategory, SourceType
from app.domain.event import Event
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.graph.state import RadarState


def build_source_item() -> SourceItem:
    return SourceItem(
        title="New radar publication",
        url="https://example.com/article",
        source_name="Example source",
        published_at=datetime.now(timezone.utc),
        content="A publication about an emerging event.",
        source_type=SourceType.MEDIA,
    )


def build_opportunity(title: str) -> Opportunity:
    return Opportunity(
        title=title,
        description="Publish an analysis of the signal.",
        why_now="The pattern is newly visible.",
        category=OpportunityCategory.CONTENT,
        impact_score=80,
        timing_score=90,
        novelty_score=70,
        content_potential=95,
        business_potential=40,
        evidence_confidence=85,
        signal_id=uuid4(),
    )


def test_radar_state_can_start_with_empty_collections() -> None:
    state: RadarState = {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    assert state["run_id"] == "run-001"
    assert all(not state[field] for field in state if field != "run_id")


def test_radar_state_accepts_existing_domain_models() -> None:
    source_item = build_source_item()
    event = Event(
        title="Grouped event",
        summary="The same event reported by a source.",
        source_items=[source_item],
    )
    signal = Signal(
        title="Growing adoption",
        description="The event shows increasing adoption.",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["technology"],
        related_event_ids=[event.id],
    )
    evidence = Evidence(
        signal_id=signal.id,
        source_item_id=source_item.id,
        evidence_type=EvidenceType.SUPPORTING,
        explanation="The source directly supports the signal.",
        confidence=75,
    )
    opportunity = build_opportunity("Create an analysis")
    state: RadarState = {
        "run_id": "run-002",
        "source_items": [source_item],
        "events": [event],
        "signals": [signal],
        "evidence": [evidence],
        "opportunities": [opportunity],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {},
    }

    assert state["source_items"] == [source_item]
    assert state["events"] == [event]
    assert state["signals"] == [signal]
    assert state["evidence"] == [evidence]
    assert state["opportunities"] == [opportunity]


def test_ranked_opportunities_are_separate_from_opportunities() -> None:
    opportunity = build_opportunity("First opportunity")
    ranked_opportunity = build_opportunity("Ranked opportunity")
    state: RadarState = {
        "run_id": "run-003",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [opportunity],
        "ranked_opportunities": [ranked_opportunity],
        "errors": [],
        "metadata": {},
    }

    assert state["opportunities"] != state["ranked_opportunities"]
    assert state["opportunities"] == [opportunity]
    assert state["ranked_opportunities"] == [ranked_opportunity]


def test_radar_state_accepts_multiple_errors_and_technical_metadata() -> None:
    state: RadarState = {
        "run_id": str(uuid4()),
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": ["Source unavailable", "Event extraction failed"],
        "metadata": {"source_count": 10, "execution_ms": 1500},
    }

    assert len(state["errors"]) == 2
    assert state["metadata"] == {"source_count": 10, "execution_ms": 1500}