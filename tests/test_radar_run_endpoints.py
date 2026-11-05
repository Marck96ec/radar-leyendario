from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.dependencies import (
    get_llm_provider,
    get_run_repository,
    get_source_provider,
)
from app.domain.enums import OpportunityCategory, SourceType
from app.domain.evidence import Evidence
from app.domain.opportunity import Opportunity
from app.domain.signal import Signal
from app.domain.source_item import SourceItem
from app.main import app
from app.repositories.runs import SQLiteRunRepository


class EmptySourceProvider:
    async def fetch(self):
        return []


class EmptyLLMProvider:
    async def structured_completion(self, system_prompt, user_prompt, response_model):
        raise AssertionError("the empty workflow should not call the LLM")


def test_run_can_be_recovered_with_safe_retry_and_opportunity_routes(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    app.dependency_overrides.update(
        {
            get_llm_provider: EmptyLLMProvider,
            get_source_provider: EmptySourceProvider,
            get_run_repository: lambda: repository,
        }
    )
    run_id = uuid4()
    client = TestClient(app)
    try:
        first = client.post("/api/v1/radar/run", json={"run_id": str(run_id)})
        retry = client.post("/api/v1/radar/run", json={"run_id": str(run_id)})
        details = client.get(f"/api/v1/radar/runs/{run_id}")
        opportunities = client.get(
            f"/api/v1/radar/runs/{run_id}/opportunities"
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert retry.status_code == 200
    assert retry.json()["run_id"] == str(run_id)
    assert details.status_code == 200
    assert details.json()["execution_trace"][-1] == "rank_opportunities"
    assert opportunities.status_code == 200
    assert opportunities.json() == []


def test_run_id_input_is_validated() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/radar/run",
        json={"run_id": "not-a-uuid"},
    )
    assert response.status_code == 422
    assert response.status_code == 422

def test_opportunity_routes_return_persisted_evidence_and_sources(tmp_path) -> None:
    repository = SQLiteRunRepository(str(tmp_path / "runs.sqlite3"))
    run_id = str(uuid4())
    source = SourceItem(
        title="Source title",
        url="https://example.test/source",
        source_name="Example",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        content="Grounded source content",
        source_type=SourceType.MEDIA,
    )
    signal = Signal(
        title="Signal title",
        description="Signal description",
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
        title="Opportunity title",
        signal_id=signal.id,
        description="Opportunity description",
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
        "run_id": run_id,
        "source_items": [source],
        "events": [],
        "signals": [signal],
        "evidence": [evidence],
        "opportunities": [opportunity],
        "ranked_opportunities": [opportunity],
        "errors": [],
        "metadata": {"execution_trace": ["rank_opportunities"]},
    }
    repository.create_running(run_id, "2026-01-01T00:00:00+00:00")
    repository.save_completed(
        state,
        "2026-01-01T00:00:00+00:00",
        "2026-01-01T00:00:01+00:00",
        1000.0,
    )
    app.dependency_overrides[get_run_repository] = lambda: repository
    client = TestClient(app)

    try:
        opportunities_response = client.get(
            f"/api/v1/radar/runs/{run_id}/opportunities"
        )
        opportunity_response = client.get(
            f"/api/v1/radar/runs/{run_id}/opportunities/{opportunity.id}"
        )
    finally:
        app.dependency_overrides.clear()

    assert opportunities_response.status_code == 200
    assert opportunity_response.status_code == 200

    opportunities_payload = opportunities_response.json()
    opportunity_payload = opportunity_response.json()
    assert len(opportunities_payload) == 1
    assert opportunity_payload == opportunities_payload[0]
    assert opportunity_payload["id"] == str(opportunity.id)
    assert opportunity_payload["evidences"] == [
        {
            "id": str(evidence.id),
            "signal_id": str(signal.id),
            "source_item_id": str(source.id),
            "evidence_type": "SUPPORTING",
            "explanation": "The source supports the signal.",
            "confidence": 90.0,
        }
    ]
    assert opportunity_payload["sources"] == [
        {
            "id": str(source.id),
            "title": "Source title",
            "url": "https://example.test/source",
            "source_name": "Example",
            "published_at": "2026-01-01T00:00:00Z",
            "source_type": "MEDIA",
        }
    ]
    assert {
        item["source_item_id"] for item in opportunity_payload["evidences"]
    } == {item["id"] for item in opportunity_payload["sources"]}
    assert {
        item["signal_id"] for item in opportunity_payload["evidences"]
    } == {str(signal.id)}
