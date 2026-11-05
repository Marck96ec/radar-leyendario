from datetime import datetime, timezone
from uuid import uuid4

from app.domain.enums import OpportunityCategory, SourceType
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.repositories.runs import SQLiteRunRepository


def test_sqlite_run_repository_round_trips_completed_state(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    state = {
        "run_id": "run-001",
        "source_items": [],
        "events": [],
        "signals": [],
        "evidence": [],
        "opportunities": [],
        "ranked_opportunities": [],
        "errors": [],
        "metadata": {"execution_trace": ["rank_opportunities"]},
    }

    repository.create_running("run-001", "2026-01-01T00:00:00+00:00")
    repository.save_completed(
        state,
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        1000.0,
    )

    record = repository.get("run-001")
    assert record is not None
    assert record.status == "completed"
    assert record.duration_ms == 1000.0
    assert record.state is not None
    assert record.state["metadata"]["execution_trace"] == ["rank_opportunities"]


def test_sqlite_run_repository_keeps_failed_status(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    repository.create_running("run-002", "2026-01-01T00:00:00+00:00")
    repository.save_failed(
        "run-002",
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:02+00:00",
        2000.0,
        "TimeoutError",
    )

    record = repository.get("run-002")
    assert record is not None
    assert record.status == "failed"
    assert record.error == "TimeoutError"


def test_sqlite_run_repository_round_trips_opportunities_and_evidence(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    source = SourceItem(
        title="Source",
        url="https://example.test/source",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="Grounded content",
        source_type=SourceType.MEDIA,
    )
    signal = Signal(
        title="Signal",
        description="A signal",
        relevance_score=80,
        novelty_score=70,
        confidence_score=90,
        topics=["technology"],
        related_event_ids=[uuid4()],
    )
    evidence = Evidence(
        signal_id=signal.id,
        source_item_id=source.id,
        evidence_type="SUPPORTING",
        explanation="The source supports the signal.",
        confidence=90,
    )
    opportunity = Opportunity(
        title="Opportunity",
        signal_id=signal.id,
        description="A grounded opportunity",
        why_now="The source is recent.",
        category=OpportunityCategory.BUSINESS,
        impact_score=80,
        timing_score=75,
        novelty_score=70,
        content_potential=60,
        business_potential=90,
        evidence_confidence=90,
        final_score=80,
    )
    state = {
        "run_id": "run-003",
        "source_items": [source],
        "events": [],
        "signals": [signal],
        "evidence": [evidence],
        "opportunities": [opportunity],
        "ranked_opportunities": [opportunity],
        "errors": [],
        "metadata": {"execution_trace": ["rank_opportunities"]},
    }

    repository.create_running("run-003", "2026-01-01T00:00:00+00:00")
    repository.save_completed(
        state,
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        1000.0,
    )

    recovered = repository.get("run-003")
    assert recovered is not None
    assert recovered.state is not None
    assert recovered.state["ranked_opportunities"][0].id == opportunity.id
    assert recovered.state["evidence"][0].source_item_id == source.id
