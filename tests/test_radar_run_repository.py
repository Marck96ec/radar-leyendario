from datetime import datetime, timezone
from uuid import uuid4

from app.domain.enums import OpportunityCategory, SourceType
from app.domain.event import Event
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.infrastructure.database.radar_run_repository import (
    InMemoryRadarRunRepository,
    SQLiteRadarRunRepository,
)
from app.graph.state import RadarState


def build_state() -> RadarState:
    source_item = SourceItem(
        title="Source",
        url="https://example.test/source",
        source_name="Example",
        published_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        content="Content",
        source_type=SourceType.OFFICIAL,
    )
    event = Event(title="Event", summary="Summary", source_items=[source_item])
    signal = Signal(
        title="Signal",
        description="Description",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["topic"],
        related_event_ids=[event.id],
    )
    opportunity = Opportunity(
        title="Opportunity",
        signal_id=signal.id,
        description="Description",
        why_now="Now",
        category=OpportunityCategory.CONTENT,
        impact_score=80,
        timing_score=70,
        novelty_score=60,
        content_potential=50,
        business_potential=40,
        evidence_confidence=30,
        final_score=60.5,
    )
    return {
        "run_id": str(uuid4()),
        "source_items": [source_item],
        "events": [event],
        "signals": [signal],
        "evidence": [],
        "opportunities": [opportunity],
        "ranked_opportunities": [opportunity],
        "errors": [],
        "metadata": {"execution_trace": ["rank_opportunities"]},
    }


def test_in_memory_repository_saves_and_returns_a_copy() -> None:
    repository = InMemoryRadarRunRepository()
    state = build_state()

    repository.save(state)
    result = repository.get_by_id(state["run_id"])

    assert result == state
    assert result is not state
    assert repository.get_by_id(str(uuid4())) is None


def test_sqlite_repository_recovers_after_repository_restart(tmp_path) -> None:
    database_path = str(tmp_path / "radar-runs.sqlite3")
    state = build_state()

    SQLiteRadarRunRepository(database_path).save(state)
    recovered = SQLiteRadarRunRepository(database_path).get_by_id(state["run_id"])

    assert recovered == state
    assert recovered is not None
    assert recovered["signals"][0].related_event_ids == [recovered["events"][0].id]
    assert recovered["ranked_opportunities"][0].final_score == 60.5
    assert recovered["ranked_opportunities"][0].category == OpportunityCategory.CONTENT


def test_sqlite_repository_preserves_missing_final_score(tmp_path) -> None:
    database_path = str(tmp_path / "radar-runs.sqlite3")
    state = build_state()
    state["ranked_opportunities"][0] = state["ranked_opportunities"][0].model_copy(
        update={"final_score": None}
    )

    SQLiteRadarRunRepository(database_path).save(state)
    recovered = SQLiteRadarRunRepository(database_path).get_by_id(state["run_id"])

    assert recovered is not None
    assert recovered["ranked_opportunities"][0].final_score is None
